"""Cricket Poller — THE HEARTBEAT of CalledIt.

Polls CricAPI every 5 seconds during live matches.
For each new delivery: close window → classify → append → resolve → emit → reopen.
"""

import asyncio
import logging

from app.redis_client import get_redis
from app.services import cricket_data_service, match_service
from app.services.ml_service import get_ball_probabilities, get_win_probability
from app.utils.constants import BallOutcome, MatchStatus
from app.utils.helpers import ball_key, classify_delivery_outcome, utc_now
from app.websocket.events import (
    emit_ball_update,
    emit_prediction_window,
    emit_score_update,
    emit_match_status_change,
    emit_ai_commentary,
    emit_over_summary,
)
from app.workers.score_processor import process_ball_result, process_match_result

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds
_running = False


async def start_poller() -> None:
    """Start the cricket polling loop. Runs until stopped."""
    global _running
    _running = True
    logger.info("Cricket poller started")

    while _running:
        try:
            await _poll_cycle()
        except Exception as e:
            logger.error(f"Poller cycle error: {e}", exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)


def stop_poller() -> None:
    """Signal the poller to stop."""
    global _running
    _running = False
    logger.info("Cricket poller stopped")


async def _poll_cycle() -> None:
    """Single polling cycle: check upcoming matches for start + live matches for new deliveries."""
    # Fetch currentMatches once per cycle (shared across all checks)
    current_matches = await cricket_data_service.fetch_current_matches()

    # Check upcoming matches that may have started
    await _check_upcoming_matches(current_matches)

    live_matches = await match_service.get_live_matches()
    if not live_matches:
        return

    for match in live_matches:
        try:
            await _poll_match(match, current_matches)
        except Exception as e:
            logger.error(f"Error polling match {match['_id']}: {e}", exc_info=True)


async def _check_upcoming_matches(current_matches: list[dict]) -> None:
    """Check if any upcoming matches have started (toss done, play started)."""
    if not current_matches:
        return

    from app.database import get_db
    db = get_db()
    upcoming = await db.matches.find(
        {"status": {"$in": [MatchStatus.UPCOMING, MatchStatus.TOSS]}, "cricapi_id": {"$ne": None}}
    ).to_list(length=50)

    if not upcoming:
        return

    for match in upcoming:
        try:
            cricapi_id = match["cricapi_id"]
            for m in current_matches:
                if m.get("id") != cricapi_id:
                    continue

                api_status = m.get("status", "").lower()
                match_started = m.get("matchStarted", False)
                match_ended = m.get("matchEnded", False)

                prev_status = match.get("status")

                # Detect toss from status text when tossWinner field is missing
                toss_winner = m.get("tossWinner")
                toss_decision = m.get("tossChoice")
                toss_keywords = ["opt to bat", "opt to bowl", "elected to", "chose to"]
                toss_detected = toss_winner or any(kw in api_status for kw in toss_keywords)

                if not toss_winner and toss_detected:
                    # Parse toss info from status text (e.g., "Sri Lanka opt to bowl")
                    toss_winner, toss_decision = _parse_toss_from_status(
                        m.get("status", ""), m.get("teams", [])
                    )

                # Match has started — transition to LIVE_1ST (from UPCOMING or TOSS)
                if match_started or "inning" in api_status:
                    await match_service.update_match_status(match["_id"], MatchStatus.LIVE_1ST)
                    if toss_winner:
                        await db.matches.update_one(
                            {"_id": match["_id"]},
                            {"$set": {
                                "toss_winner": toss_winner,
                                "toss_decision": toss_decision,
                            }},
                        )
                    await emit_match_status_change(match["_id"], MatchStatus.LIVE_1ST)
                    await match_service.open_prediction_window(match["_id"])
                    await emit_prediction_window(match["_id"], True, "1.1.1")
                    logger.info(f"Match {match['_id']}: {prev_status} → LIVE_1ST")

                # Match ended while still upcoming/toss (abandoned before play)
                elif match_ended:
                    await _finalize_ended_match(match, m)
                    logger.info(f"Match {match['_id']}: {prev_status} → ended (abandoned/completed)")

                # Toss done but match not started yet (only for UPCOMING)
                elif prev_status == MatchStatus.UPCOMING and toss_detected and not match_started:
                    await match_service.update_match_status(match["_id"], MatchStatus.TOSS)
                    update_fields = {"result_text": m.get("status", "")}
                    if toss_winner:
                        update_fields["toss_winner"] = toss_winner
                        update_fields["toss_decision"] = toss_decision
                    await db.matches.update_one(
                        {"_id": match["_id"]},
                        {"$set": update_fields},
                    )
                    await emit_match_status_change(match["_id"], MatchStatus.TOSS)
                    logger.info(f"Match {match['_id']}: UPCOMING → TOSS ({m.get('status', '')})")
                break
        except Exception as e:
            logger.error(f"Error checking upcoming match {match['_id']}: {e}", exc_info=True)


async def _poll_match(match: dict, current_matches: list[dict]) -> None:
    """Poll a single live match for new deliveries."""
    match_id = match["_id"]
    cricapi_id = match.get("cricapi_id")
    if not cricapi_id:
        return

    redis = get_redis()
    ball_count_key = f"match_balls:{match_id}"

    # Get current ball count
    prev_count = int(await redis.get(ball_count_key) or 0)

    # Fetch latest ball-by-ball data from CricAPI
    bbb_data = await cricket_data_service.fetch_match_ball_by_ball(cricapi_id)
    if not bbb_data:
        # No bbb data — could be abandoned/no play. Check currentMatches for status.
        await _check_live_match_ended(match, current_matches)
        return

    # Detect new deliveries
    new_deliveries = cricket_data_service.detect_new_deliveries(prev_count, bbb_data)
    if not new_deliveries:
        # Check for match status changes even if no new balls
        await _check_status_change(match, bbb_data, current_matches)
        return

    logger.info(f"Match {match_id}: {len(new_deliveries)} new deliveries detected")

    for delivery in new_deliveries:
        await _process_delivery(match_id, delivery)

    # Update ball count in Redis
    new_total = prev_count + len(new_deliveries)
    await redis.set(ball_count_key, new_total)


async def _process_delivery(match_id: str, delivery: dict) -> None:
    """Process a single new delivery: score → resolve → emit → reopen window."""
    # 1. Close prediction window
    await match_service.close_prediction_window(match_id)
    await emit_prediction_window(match_id, False)

    # 2. Classify outcome
    outcome = classify_delivery_outcome(delivery)

    # 3. Build ball entry
    now = utc_now()
    bk = ball_key(delivery["innings"], delivery["over"], delivery["ball"])
    ball_entry = {
        "innings": delivery["innings"],
        "over": delivery["over"],
        "ball": delivery["ball"],
        "ball_key": bk,
        "batter": delivery.get("batter", ""),
        "bowler": delivery.get("bowler", ""),
        "non_striker": delivery.get("non_striker", ""),
        "batter_runs": delivery.get("batter_runs", 0),
        "extras": delivery.get("extras", 0),
        "total_runs": delivery.get("total_runs", 0),
        "outcome": outcome.value,
        "is_wicket": delivery.get("is_wicket", False),
        "wicket_kind": delivery.get("wicket_kind"),
        "player_out": delivery.get("player_out"),
        "timestamp": now,
    }

    # 4. Append to match ball_log
    await match_service.append_ball(match_id, ball_entry)

    # 5. Resolve predictions and score
    await process_ball_result(match_id, bk, outcome.value, delivery["over"])

    # 6. Emit WebSocket events
    await emit_ball_update(match_id, ball_entry)
    await emit_score_update(match_id, {
        "innings": delivery["innings"],
        "over": delivery["over"],
        "ball": delivery["ball"],
        "total_runs": delivery.get("total_runs", 0),
    })

    # 7. Get ML probabilities for next ball
    try:
        ml_probs = await get_ball_probabilities(match_id)
        await get_win_probability(match_id)  # updates cached state
    except Exception as e:
        logger.warning(f"ML prediction error: {e}")
        ml_probs = {}

    # 8. Generate AI commentary for significant events
    if outcome in (BallOutcome.WICKET, BallOutcome.SIX, BallOutcome.FOUR):
        try:
            from app.services.ai_content_service import generate_ball_commentary
            commentary = await generate_ball_commentary(
                match_id, ball_entry, ml_probs.get("probabilities", {})
            )
            ball_entry["commentary"] = commentary
            await emit_ai_commentary(match_id, commentary, bk)
        except Exception as e:
            logger.warning(f"AI commentary error: {e}")

    # 9. Check if over is complete (6 legal deliveries)
    if delivery["ball"] == 6:
        await _handle_over_complete(match_id, delivery["innings"], delivery["over"])

    # 10. Re-open prediction window for next ball
    await match_service.open_prediction_window(match_id)
    next_bk = ball_key(delivery["innings"], delivery["over"], delivery["ball"] + 1)
    await emit_prediction_window(match_id, True, next_bk)


async def _handle_over_complete(match_id: str, innings: int, over: int) -> None:
    """Handle end-of-over: resolve over predictions, generate summary."""
    from app.services.prediction_service import resolve_over_predictions

    # Get total runs in this over from ball_log
    match = await match_service.get_match(match_id)
    if not match:
        return

    balls_in_over = [
        b for b in match.get("ball_log", [])
        if b.get("innings") == innings and b.get("over") == over
    ]
    over_runs = sum(b.get("total_runs", 0) for b in balls_in_over)

    await resolve_over_predictions(match_id, innings, over, over_runs)

    # Generate over summary and emit via WebSocket
    try:
        from app.services.ai_content_service import generate_over_summary
        summary = await generate_over_summary(match_id, innings, over, balls_in_over)
        await emit_over_summary(match_id, innings, over, summary)
    except Exception as e:
        logger.warning(f"Over summary generation error: {e}")


async def _check_live_match_ended(match: dict, current_matches: list[dict]) -> None:
    """Check currentMatches data for a live match that may have ended (abandoned, no play, etc.)."""
    cricapi_id = match.get("cricapi_id")
    if not cricapi_id:
        return

    for m in current_matches:
        if m.get("id") != cricapi_id:
            continue

        if m.get("matchEnded"):
            await _finalize_ended_match(match, m)
        break


async def _finalize_ended_match(match: dict, cricapi_match: dict) -> None:
    """Handle a match that CricAPI reports as ended (completed or abandoned)."""
    match_id = match["_id"]
    status_text = cricapi_match.get("status", "")
    winner = _extract_winner(cricapi_match)

    # Close prediction window
    await match_service.close_prediction_window(match_id)

    if winner:
        # Normal completion with a winner
        await match_service.complete_match(match_id, winner, status_text)
        await emit_match_status_change(match_id, MatchStatus.COMPLETED)
        await process_match_result(match_id, winner)
        logger.info(f"Match {match_id} completed. Winner: {winner}")

        try:
            from app.services.ai_content_service import generate_post_match_report
            await generate_post_match_report(match_id)
        except Exception as e:
            logger.warning(f"Post-match report error: {e}")
    else:
        # No winner — abandoned, no result, rain, etc.
        from app.database import get_db
        db = get_db()
        await db.matches.update_one(
            {"_id": match_id},
            {"$set": {
                "status": MatchStatus.ABANDONED,
                "result_text": status_text or "Match abandoned",
                "prediction_window_open": False,
                "updated_at": utc_now(),
            }},
        )
        await emit_match_status_change(match_id, MatchStatus.ABANDONED)
        logger.info(f"Match {match_id} abandoned: {status_text}")


async def _check_status_change(match: dict, bbb_data: dict, current_matches: list[dict]) -> None:
    """Check if match status has changed (e.g., innings break, completed)."""
    match_id = match["_id"]
    current_status = match.get("status")

    # Detect innings break
    innings_data = bbb_data.get("bbb", [])
    num_innings = len(innings_data)

    if current_status == MatchStatus.LIVE_1ST and num_innings >= 2:
        await match_service.update_match_status(match_id, MatchStatus.LIVE_2ND)
        await emit_match_status_change(match_id, MatchStatus.LIVE_2ND)
        logger.info(f"Match {match_id}: Innings break → 2nd innings")

    # Detect match completion via currentMatches data
    cricapi_id = match.get("cricapi_id")
    if cricapi_id:
        for m in current_matches:
            if m.get("id") == cricapi_id and m.get("matchEnded"):
                await _finalize_ended_match(match, m)
                break


def _extract_winner(cricapi_match: dict) -> str:
    """Extract winner team name from CricAPI match data."""
    status = cricapi_match.get("status", "")
    teams = cricapi_match.get("teamInfo", [])

    # CricAPI status field usually says "TeamName won by X runs/wickets"
    for team in teams:
        name = team.get("name", "")
        if name and name.lower() in status.lower():
            if "won" in status.lower():
                return name
    return ""


def _parse_toss_from_status(status_text: str, teams: list[str]) -> tuple[str, str]:
    """Parse toss winner and decision from CricAPI status text.

    Examples: "Sri Lanka opt to bowl", "England elected to bat first"
    Returns (toss_winner, toss_decision) or ("", "").
    """
    s = status_text.lower()
    decision = ""
    if "opt to bat" in s or "elected to bat" in s or "chose to bat" in s:
        decision = "bat"
    elif "opt to bowl" in s or "elected to bowl" in s or "chose to bowl" in s or "elected to field" in s:
        decision = "bowl"

    if not decision:
        return "", ""

    # Try to find which team from the status text
    for team in teams:
        if team.lower() in s:
            return team, decision

    # Fallback: the text before "opt"/"elected"/"chose" is likely the team name
    for keyword in ["opt to", "elected to", "chose to"]:
        if keyword in s:
            team_part = s.split(keyword)[0].strip()
            if team_part:
                # Capitalise properly
                return status_text[:len(team_part)].strip(), decision

    return "", decision
