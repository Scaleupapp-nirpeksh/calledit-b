import logging
from typing import Optional

import httpx

from app.config import settings
from app.database import get_db
from app.utils.constants import BallOutcome, MatchStatus
from app.utils.helpers import classify_delivery_outcome, generate_nanoid, utc_now

logger = logging.getLogger(__name__)


async def fetch_current_matches() -> list[dict]:
    """GET /currentMatches from CricAPI — returns list of current/recent matches."""
    url = f"{settings.CRICAPI_BASE_URL}/currentMatches"
    params = {"apikey": settings.CRICAPI_KEY, "offset": 0}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "success":
        logger.warning(f"CricAPI currentMatches failed: {data}")
        return []
    return data.get("data", [])


# Platform-supported series (CricAPI series ID → competition _id)
SUPPORTED_SERIES: dict[str, str] = {
    "0cdf6736-ad9b-4e95-a647-5ee3a99c5510": "comp_t20wc_2026",
    # Add IPL 2026 series ID here when CricAPI publishes it
}


async def fetch_series_matches(series_id: str) -> list[dict]:
    """GET /series_info from CricAPI — returns all matches in a series."""
    url = f"{settings.CRICAPI_BASE_URL}/series_info"
    params = {"apikey": settings.CRICAPI_KEY, "id": series_id}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "success":
        logger.warning(f"CricAPI series_info failed: {data}")
        return []
    return data.get("data", {}).get("matchList", [])


async def sync_series_to_db(series_id: str, competition_id: str) -> list[str]:
    """Sync all matches from a CricAPI series, linked to a competition."""
    matches = await fetch_series_matches(series_id)
    db = get_db()
    synced_ids = []

    for m in matches:
        cricapi_id = m.get("id", "")
        if not cricapi_id:
            continue

        status = _map_cricapi_status(m)
        teams = m.get("teamInfo", [])
        team1 = teams[0] if len(teams) > 0 else {}
        team2 = teams[1] if len(teams) > 1 else {}
        match_teams = m.get("teams", [])

        now = utc_now()
        match_doc = {
            "cricapi_id": cricapi_id,
            "name": m.get("name", ""),
            "match_type": "T20",
            "status": status,
            "venue": m.get("venue", ""),
            "date": m.get("date", now.isoformat()),
            "team1": team1.get("name", match_teams[0] if match_teams else ""),
            "team2": team2.get("name", match_teams[1] if len(match_teams) > 1 else ""),
            "team1_code": team1.get("shortname", ""),
            "team2_code": team2.get("shortname", ""),
            "team1_img": team1.get("img"),
            "team2_img": team2.get("img"),
            "toss_winner": m.get("tossWinner"),
            "toss_decision": m.get("tossChoice"),
            "result_text": m.get("status"),
            "winner": m.get("matchWinner"),
            "score": m.get("score", []),
            "competition_id": competition_id,
            "updated_at": now,
        }

        existing = await db.matches.find_one({"cricapi_id": cricapi_id})
        if existing:
            await db.matches.update_one({"_id": existing["_id"]}, {"$set": match_doc})
            synced_ids.append(existing["_id"])
        else:
            match_id = generate_nanoid()
            match_doc["_id"] = match_id
            match_doc["innings"] = []
            match_doc["ball_log"] = []
            match_doc["scorecard"] = None
            match_doc["ai_preview"] = None
            match_doc["prediction_window_open"] = False
            match_doc["current_innings"] = None
            match_doc["current_over"] = None
            match_doc["current_ball"] = None
            match_doc["win_probability_timeline"] = []
            match_doc["created_at"] = now
            await db.matches.insert_one(match_doc)
            synced_ids.append(match_id)

    # Update competition match count
    total = await db.matches.count_documents({"competition_id": competition_id})
    await db.competitions.update_one(
        {"_id": competition_id},
        {"$set": {"match_count": total, "updated_at": utc_now()}},
    )
    logger.info(f"Synced {len(synced_ids)} matches for competition {competition_id}")
    return synced_ids


async def sync_all_supported_series() -> dict[str, int]:
    """Sync all platform-supported series (IPL + T20WC)."""
    results = {}
    for series_id, comp_id in SUPPORTED_SERIES.items():
        ids = await sync_series_to_db(series_id, comp_id)
        results[comp_id] = len(ids)
    return results


async def enrich_completed_matches() -> int:
    """Fetch scorecards for completed matches that don't have scorecard data yet."""
    db = get_db()
    cursor = db.matches.find({
        "status": MatchStatus.COMPLETED,
        "scorecard": None,
        "cricapi_id": {"$ne": None},
    })
    matches = await cursor.to_list(length=200)
    enriched = 0

    for match in matches:
        cricapi_id = match["cricapi_id"]
        try:
            data = await fetch_match_scorecard(cricapi_id)
            if not data:
                continue

            update = {}
            # Store full scorecard (batting, bowling per innings)
            if data.get("scorecard"):
                update["scorecard"] = data["scorecard"]
            # Store score summary if not already present
            if data.get("score") and not match.get("score"):
                update["score"] = data["score"]
            # Store winner if not already present
            if data.get("matchWinner") and not match.get("winner"):
                update["winner"] = data["matchWinner"]
            # Store toss if not already present
            if data.get("tossWinner") and not match.get("toss_winner"):
                update["toss_winner"] = data["tossWinner"]
                update["toss_decision"] = data.get("tossChoice")
            # Store team images if not already present
            team_info = data.get("teamInfo", [])
            if team_info and not match.get("team1_img"):
                if len(team_info) > 0:
                    update["team1_img"] = team_info[0].get("img")
                if len(team_info) > 1:
                    update["team2_img"] = team_info[1].get("img")

            if update:
                update["updated_at"] = utc_now()
                await db.matches.update_one({"_id": match["_id"]}, {"$set": update})
                enriched += 1
                logger.info(f"Enriched match {match['_id']} ({match.get('name', '')})")
        except Exception as e:
            logger.warning(f"Failed to enrich match {match['_id']}: {e}")

    logger.info(f"Enriched {enriched}/{len(matches)} completed matches")
    return enriched


async def fetch_match_scorecard(cricapi_id: str) -> Optional[dict]:
    """GET /match_scorecard from CricAPI — returns full scorecard for a match."""
    url = f"{settings.CRICAPI_BASE_URL}/match_scorecard"
    params = {"apikey": settings.CRICAPI_KEY, "id": cricapi_id}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "success":
        logger.warning(f"CricAPI scorecard failed for {cricapi_id}: {data}")
        return None
    return data.get("data")


async def fetch_match_ball_by_ball(cricapi_id: str) -> Optional[dict]:
    """GET /match_bbb from CricAPI — returns ball-by-ball data."""
    url = f"{settings.CRICAPI_BASE_URL}/match_bbb"
    params = {"apikey": settings.CRICAPI_KEY, "id": cricapi_id}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "success":
        logger.warning(f"CricAPI bbb failed for {cricapi_id}: {data}")
        return None
    return data.get("data")


async def sync_match_to_db(cricapi_match: dict, match_type_filter: str = "T20") -> Optional[str]:
    """Upsert a CricAPI match into our matches collection. Returns match _id or None if filtered."""
    # Filter by match type
    api_match_type = cricapi_match.get("matchType", "")
    if match_type_filter != "all" and api_match_type.upper() != match_type_filter.upper():
        return None

    db = get_db()
    cricapi_id = cricapi_match.get("id")

    existing = await db.matches.find_one({"cricapi_id": cricapi_id})

    status = _map_cricapi_status(cricapi_match)

    teams = cricapi_match.get("teamInfo", [])
    team1 = teams[0] if len(teams) > 0 else {}
    team2 = teams[1] if len(teams) > 1 else {}

    now = utc_now()
    match_doc = {
        "cricapi_id": cricapi_id,
        "name": cricapi_match.get("name", ""),
        "match_type": cricapi_match.get("matchType", "T20"),
        "status": status,
        "venue": cricapi_match.get("venue", ""),
        "date": cricapi_match.get("date", now.isoformat()),
        "team1": team1.get("name", ""),
        "team2": team2.get("name", ""),
        "team1_code": team1.get("shortname", ""),
        "team2_code": team2.get("shortname", ""),
        "team1_img": team1.get("img"),
        "team2_img": team2.get("img"),
        "toss_winner": cricapi_match.get("tossWinner"),
        "toss_decision": cricapi_match.get("tossChoice"),
        "result_text": cricapi_match.get("status"),
        "winner": cricapi_match.get("matchWinner"),
        "score": cricapi_match.get("score", []),
        "updated_at": now,
    }

    if existing:
        await db.matches.update_one({"_id": existing["_id"]}, {"$set": match_doc})
        return existing["_id"]
    else:
        match_id = generate_nanoid()
        match_doc["_id"] = match_id
        match_doc["innings"] = []
        match_doc["ball_log"] = []
        match_doc["scorecard"] = None
        match_doc["ai_preview"] = None
        match_doc["prediction_window_open"] = False
        match_doc["current_innings"] = None
        match_doc["current_over"] = None
        match_doc["current_ball"] = None
        match_doc["competition_id"] = None
        match_doc["win_probability_timeline"] = []
        match_doc["created_at"] = now
        await db.matches.insert_one(match_doc)

        # Auto-assign to competition
        try:
            from app.services.competition_service import auto_assign_match_to_competition
            await auto_assign_match_to_competition(match_doc)
        except Exception as e:
            logger.warning(f"Competition auto-assign failed for {match_id}: {e}")

        return match_id


def detect_new_deliveries(
    prev_ball_count: int, current_bbb: dict
) -> list[dict]:
    """Given previous delivery count and current ball-by-ball data,
    extract only the new deliveries."""
    all_deliveries = _extract_deliveries_from_bbb(current_bbb)
    if len(all_deliveries) <= prev_ball_count:
        return []
    return all_deliveries[prev_ball_count:]


def classify_delivery(delivery: dict) -> BallOutcome:
    """Classify a CricAPI delivery into one of 7 outcomes."""
    return classify_delivery_outcome(delivery)


def _map_cricapi_status(match: dict) -> str:
    """Map CricAPI match status to our MatchStatus enum."""
    started = match.get("matchStarted", False)
    ended = match.get("matchEnded", False)

    if not started and not ended:
        return MatchStatus.UPCOMING
    elif started and not ended:
        return MatchStatus.LIVE_1ST  # Refined by poller based on innings data
    elif started and ended:
        # Check if abandoned/no result vs normal completion
        status_text = match.get("status", "").lower()
        abandon_keywords = ["abandon", "no result", "no match", "cancelled", "postponed"]
        if any(kw in status_text for kw in abandon_keywords):
            return MatchStatus.ABANDONED
        if not match.get("matchWinner") and "won" not in status_text:
            return MatchStatus.ABANDONED
        return MatchStatus.COMPLETED
    return MatchStatus.UPCOMING


def _extract_deliveries_from_bbb(bbb_data: dict) -> list[dict]:
    """Extract flat list of deliveries from CricAPI ball-by-ball response."""
    deliveries = []
    if not bbb_data:
        return deliveries

    for innings_data in bbb_data.get("bbb", []):
        innings_num = innings_data.get("inning", 1)
        for over_data in innings_data.get("overs", []):
            over_num = over_data.get("over", 0)
            for ball_idx, ball in enumerate(over_data.get("balls", []), start=1):
                deliveries.append({
                    "innings": innings_num,
                    "over": over_num + 1,  # 0-indexed to 1-indexed
                    "ball": ball_idx,
                    "batter": ball.get("batter", {}).get("name", ""),
                    "bowler": ball.get("bowler", {}).get("name", ""),
                    "non_striker": ball.get("non_striker", {}).get("name", ""),
                    "batter_runs": ball.get("run", 0),
                    "extras": ball.get("extras", 0),
                    "total_runs": ball.get("run", 0) + ball.get("extras", 0),
                    "is_wicket": ball.get("wicket", False),
                    "wicket_kind": ball.get("wicket_type"),
                    "player_out": ball.get("player_out"),
                    "raw": ball,
                })

    return deliveries
