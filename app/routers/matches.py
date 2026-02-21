from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import get_db
from app.services import match_service

router = APIRouter(prefix="/matches", tags=["Matches"])


@router.get("")
async def list_matches(
    status: Optional[str] = None,
    date_filter: Optional[str] = Query(None, alias="date"),
    team: Optional[str] = None,
    competition_id: Optional[str] = Query(None, description="Filter by competition"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Get matches with optional filters (status, date, team, competition)."""
    matches, total = await match_service.get_matches(
        status_filter=status,
        date_filter=date_filter,
        team_filter=team,
        competition_id=competition_id,
        limit=limit,
        offset=offset,
    )
    return {"matches": _format_matches(matches), "total": total}


@router.get("/live")
async def get_live_matches():
    """Get all currently live matches."""
    matches = await match_service.get_live_matches()
    return {"matches": _format_matches(matches), "total": len(matches)}


@router.get("/{match_id}")
async def get_match(match_id: str):
    """Get a single match by ID."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return _format_match(match)


@router.get("/{match_id}/scorecard")
async def get_scorecard(match_id: str):
    """Get match scorecard — detailed batting/bowling stats per innings."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    cricapi_scorecard = match.get("scorecard")

    # If no scorecard cached, try fetching from CricAPI on demand
    if not cricapi_scorecard and match.get("cricapi_id") and match.get("status") == "completed":
        from app.services.cricket_data_service import fetch_match_scorecard
        data = await fetch_match_scorecard(match["cricapi_id"])
        if data:
            if data.get("scorecard"):
                cricapi_scorecard = data["scorecard"]
            # Cache everything we got
            update = {}
            if cricapi_scorecard:
                update["scorecard"] = cricapi_scorecard
            if data.get("score") and not match.get("score"):
                update["score"] = data["score"]
                match["score"] = data["score"]
            if update:
                db = get_db()
                await db.matches.update_one({"_id": match_id}, {"$set": update})

    # Build innings array: prefer our internal innings data, fall back to CricAPI score
    innings = match.get("innings", [])
    if not innings:
        innings = _build_innings_from_score(match)

    return {
        "match_id": match_id,
        "innings": innings,
        "ball_log": match.get("ball_log", []),
        "detailed_scorecard": cricapi_scorecard or [],
        "team1": match.get("team1", ""),
        "team2": match.get("team2", ""),
        "team1_code": match.get("team1_code", ""),
        "team2_code": match.get("team2_code", ""),
        "team1_img": match.get("team1_img"),
        "team2_img": match.get("team2_img"),
        "result_text": match.get("result_text"),
        "winner": match.get("winner"),
        "toss_winner": match.get("toss_winner"),
        "toss_decision": match.get("toss_decision"),
    }


@router.get("/{match_id}/players")
async def get_match_players(match_id: str):
    """Get player names for a match — used for milestone prediction dropdowns."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    players = {"team1": match.get("team1", ""), "team2": match.get("team2", ""),
               "team1_code": match.get("team1_code", ""), "team2_code": match.get("team2_code", ""),
               "batters": [], "bowlers": []}
    seen_batters = set()
    seen_bowlers = set()

    # Extract from scorecard (completed matches)
    for inn in match.get("scorecard", []) or []:
        for b in inn.get("batting", []):
            name = b.get("batsman", {}).get("name", "") if isinstance(b.get("batsman"), dict) else b.get("batsman", "")
            if name and name not in seen_batters:
                seen_batters.add(name)
                players["batters"].append(name)
        for b in inn.get("bowling", []):
            name = b.get("bowler", {}).get("name", "") if isinstance(b.get("bowler"), dict) else b.get("bowler", "")
            if name and name not in seen_bowlers:
                seen_bowlers.add(name)
                players["bowlers"].append(name)

    # Extract from ball_log (live matches)
    for ball in match.get("ball_log", []):
        batter = ball.get("batter", "")
        bowler = ball.get("bowler", "")
        if batter and batter not in seen_batters:
            seen_batters.add(batter)
            players["batters"].append(batter)
        if bowler and bowler not in seen_bowlers:
            seen_bowlers.add(bowler)
            players["bowlers"].append(bowler)

    return players


@router.get("/{match_id}/timeline")
async def get_timeline(match_id: str, innings: int = 1):
    """Get ball-by-ball timeline for a match innings."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    balls = [
        b for b in match.get("ball_log", [])
        if b.get("innings") == innings
    ]
    return {"match_id": match_id, "innings": innings, "balls": balls}


@router.get("/{match_id}/win-probability")
async def get_win_probability(match_id: str):
    """Get win probability timeline for a match."""
    from app.services.ml_service import get_win_probability as get_wp
    result = await get_wp(match_id)
    return result


@router.get("/{match_id}/ai-preview")
async def get_ai_preview(match_id: str):
    """Get AI pre-match brief. Auto-generates on first request, cached after."""
    db = get_db()
    ai_content = await db.ai_content.find_one(
        {"match_id": match_id, "type": "pre_match_brief"},
        sort=[("created_at", -1)],
    )
    if not ai_content:
        # Generate on demand for upcoming/live matches
        match = await match_service.get_match(match_id)
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        from app.services.ai_content_service import generate_pre_match_brief
        try:
            ai_content = await generate_pre_match_brief(match_id)
        except Exception:
            raise HTTPException(status_code=503, detail="AI generation temporarily unavailable")
    return {
        "match_id": match_id,
        "content": ai_content["content"],
        "generated_at": ai_content["created_at"],
    }


@router.get("/{match_id}/ai-report")
async def get_ai_report(match_id: str):
    """Get AI post-match report. Auto-generates on first request, cached after."""
    db = get_db()
    ai_content = await db.ai_content.find_one(
        {"match_id": match_id, "type": "post_match_report"},
        sort=[("created_at", -1)],
    )
    if not ai_content:
        match = await match_service.get_match(match_id)
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        if match.get("status") != "completed":
            raise HTTPException(status_code=404, detail="Match not completed yet")
        from app.services.ai_content_service import generate_post_match_report
        try:
            ai_content = await generate_post_match_report(match_id)
        except Exception:
            raise HTTPException(status_code=503, detail="AI generation temporarily unavailable")
    return {
        "match_id": match_id,
        "content": ai_content["content"],
        "generated_at": ai_content["created_at"],
    }


def _build_innings_from_score(match: dict) -> list[dict]:
    """Transform CricAPI score summary into our Innings[] format."""
    score_list = match.get("score", [])
    if not score_list:
        return []

    team1 = match.get("team1", "")
    team2 = match.get("team2", "")
    innings = []

    for idx, s in enumerate(score_list):
        inning_label = s.get("inning", "")
        runs = s.get("r", 0)
        wickets = s.get("w", 0)
        overs = s.get("o", 0.0)
        run_rate = round(runs / overs, 2) if overs > 0 else 0.0

        # Determine batting/bowling team from inning label (e.g. "Oman Inning 1")
        if team1 and team1.lower() in inning_label.lower():
            batting_team = team1
            bowling_team = team2
        elif team2 and team2.lower() in inning_label.lower():
            batting_team = team2
            bowling_team = team1
        else:
            batting_team = inning_label.replace(" Inning 1", "").replace(" Inning 2", "")
            bowling_team = ""

        inn = {
            "innings_number": idx + 1,
            "batting_team": batting_team,
            "bowling_team": bowling_team,
            "score": runs,
            "wickets": wickets,
            "overs": overs,
            "run_rate": run_rate,
            "target": None,
            "required_rate": None,
        }
        # Set target for 2nd innings
        if idx == 1 and len(innings) > 0:
            inn["target"] = innings[0]["score"] + 1

        innings.append(inn)

    return innings


def _format_match(m: dict) -> dict:
    return {
        "id": m["_id"],
        "cricapi_id": m.get("cricapi_id"),
        "name": m.get("name", ""),
        "match_type": m.get("match_type", "T20"),
        "status": m.get("status"),
        "venue": m.get("venue", ""),
        "date": m.get("date"),
        "team1": m.get("team1", ""),
        "team2": m.get("team2", ""),
        "team1_code": m.get("team1_code", ""),
        "team2_code": m.get("team2_code", ""),
        "team1_img": m.get("team1_img"),
        "team2_img": m.get("team2_img"),
        "toss_winner": m.get("toss_winner"),
        "toss_decision": m.get("toss_decision"),
        "score": m.get("score", []),
        "innings": m.get("innings", []),
        "winner": m.get("winner"),
        "result_text": m.get("result_text"),
        "competition_id": m.get("competition_id"),
        "ai_preview": m.get("ai_preview"),
        "prediction_window_open": m.get("prediction_window_open", False),
        "current_innings": m.get("current_innings"),
        "current_over": m.get("current_over"),
        "current_ball": m.get("current_ball"),
        "created_at": m.get("created_at"),
        "updated_at": m.get("updated_at"),
    }


def _format_matches(matches: list[dict]) -> list[dict]:
    return [_format_match(m) for m in matches]
