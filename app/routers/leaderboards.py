from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_optional_user
from app.services import leaderboard_service

router = APIRouter(prefix="/leaderboards", tags=["Leaderboards"])


@router.get("/match/{match_id}")
async def get_match_leaderboard(
    match_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
):
    """Get match leaderboard."""
    entries, total = await leaderboard_service.get_match_leaderboard(
        match_id, limit=limit, offset=offset
    )
    result = {
        "type": "match",
        "key": match_id,
        "entries": entries,
        "total_participants": total,
        "page": (offset // limit) + 1,
        "limit": limit,
    }
    if user:
        result["my_rank"] = await leaderboard_service.get_user_rank(
            user["_id"], f"lb:match:{match_id}"
        )
        result["neighbours"] = await leaderboard_service.get_user_neighbours(
            user["_id"], f"lb:match:{match_id}"
        )
    return result


@router.get("/daily")
async def get_daily_leaderboard(
    d: Optional[str] = Query(None, alias="date"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
):
    """Get daily leaderboard."""
    target_date = date.fromisoformat(d) if d else None
    entries, total = await leaderboard_service.get_daily_leaderboard(
        d=target_date, limit=limit, offset=offset
    )
    key = (target_date or date.today()).isoformat()
    result = {
        "type": "daily",
        "key": key,
        "entries": entries,
        "total_participants": total,
        "page": (offset // limit) + 1,
        "limit": limit,
    }
    if user:
        result["my_rank"] = await leaderboard_service.get_user_rank(
            user["_id"], f"lb:daily:{key}"
        )
    return result


@router.get("/season")
async def get_season_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
):
    """Get season leaderboard."""
    entries, total = await leaderboard_service.get_season_leaderboard(
        limit=limit, offset=offset
    )
    result = {
        "type": "season",
        "key": "2026",
        "entries": entries,
        "total_participants": total,
        "page": (offset // limit) + 1,
        "limit": limit,
    }
    if user:
        result["my_rank"] = await leaderboard_service.get_user_rank(
            user["_id"], "lb:season:2026"
        )
    return result


@router.get("/competition/{competition_id}")
async def get_competition_leaderboard(
    competition_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
):
    """Get competition-wide leaderboard."""
    entries, total = await leaderboard_service.get_competition_leaderboard(
        competition_id, limit=limit, offset=offset
    )
    result = {
        "type": "competition",
        "key": competition_id,
        "entries": entries,
        "total_participants": total,
        "page": (offset // limit) + 1,
        "limit": limit,
    }
    if user:
        result["my_rank"] = await leaderboard_service.get_user_rank(
            user["_id"], f"lb:competition:{competition_id}"
        )
    return result


@router.get("/league/{league_id}")
async def get_league_leaderboard(
    league_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
):
    """Get league-wide leaderboard."""
    entries, total = await leaderboard_service.get_league_leaderboard(
        league_id, limit=limit, offset=offset
    )
    result = {
        "type": "league",
        "key": league_id,
        "entries": entries,
        "total_participants": total,
        "page": (offset // limit) + 1,
        "limit": limit,
    }
    if user:
        result["my_rank"] = await leaderboard_service.get_user_rank(
            user["_id"], f"lb:league:{league_id}"
        )
    return result


@router.get("/league/{league_id}/match/{match_id}")
async def get_league_match_leaderboard(
    league_id: str,
    match_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
):
    """Get league leaderboard for a specific match."""
    entries, total = await leaderboard_service.get_league_match_leaderboard(
        league_id, match_id, limit=limit, offset=offset
    )
    result = {
        "type": "league_match",
        "key": f"{league_id}:{match_id}",
        "entries": entries,
        "total_participants": total,
        "page": (offset // limit) + 1,
        "limit": limit,
    }
    if user:
        result["my_rank"] = await leaderboard_service.get_user_rank(
            user["_id"], f"lb:league:{league_id}:match:{match_id}"
        )
    return result
