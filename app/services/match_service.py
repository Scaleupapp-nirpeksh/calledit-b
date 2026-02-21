import json
import logging
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.redis_client import get_redis
from app.utils.constants import MatchStatus, PREDICTION_WINDOW_SECONDS
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)

MATCH_CACHE_TTL = 30  # seconds


async def get_match(match_id: str) -> Optional[dict]:
    """Get a single match by ID."""
    db = get_db()
    return await db.matches.find_one({"_id": match_id})


async def get_matches(
    status_filter: Optional[str] = None,
    date_filter: Optional[str] = None,
    team_filter: Optional[str] = None,
    competition_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Get matches with optional filters. Returns (matches, total_count)."""
    db = get_db()
    query = {}
    if status_filter:
        query["status"] = status_filter
    if date_filter:
        query["date"] = {"$regex": f"^{date_filter}"}
    if team_filter:
        query["$or"] = [
            {"team1_code": team_filter},
            {"team2_code": team_filter},
            {"team1": {"$regex": team_filter, "$options": "i"}},
            {"team2": {"$regex": team_filter, "$options": "i"}},
        ]
    if competition_id:
        query["competition_id"] = competition_id
    else:
        # Default: only show matches linked to a competition (IPL/T20WC)
        query["competition_id"] = {"$ne": None}

    total = await db.matches.count_documents(query)
    cursor = db.matches.find(query).sort("date", -1).skip(offset).limit(limit)
    matches = await cursor.to_list(length=limit)
    return matches, total


async def get_live_matches() -> list[dict]:
    """Get all currently live matches."""
    db = get_db()
    live_statuses = [MatchStatus.LIVE_1ST, MatchStatus.LIVE_2ND, MatchStatus.TOSS, MatchStatus.INNINGS_BREAK]
    cursor = db.matches.find({"status": {"$in": live_statuses}}).sort("date", -1)
    return await cursor.to_list(length=20)


async def append_ball(match_id: str, ball_entry: dict) -> None:
    """Append a ball entry to the match's ball_log array."""
    db = get_db()
    now = utc_now()
    await db.matches.update_one(
        {"_id": match_id},
        {
            "$push": {"ball_log": ball_entry},
            "$set": {
                "current_innings": ball_entry.get("innings"),
                "current_over": ball_entry.get("over"),
                "current_ball": ball_entry.get("ball"),
                "updated_at": now,
            },
        },
    )
    await _invalidate_match_cache(match_id)


async def update_match_status(match_id: str, new_status: str) -> None:
    """Update match status."""
    db = get_db()
    await db.matches.update_one(
        {"_id": match_id},
        {"$set": {"status": new_status, "updated_at": utc_now()}},
    )
    await _invalidate_match_cache(match_id)


async def complete_match(match_id: str, winner: str, result_text: str = "") -> None:
    """Mark match as completed with winner."""
    db = get_db()
    await db.matches.update_one(
        {"_id": match_id},
        {
            "$set": {
                "status": MatchStatus.COMPLETED,
                "winner": winner,
                "result_text": result_text,
                "updated_at": utc_now(),
            }
        },
    )
    await _invalidate_match_cache(match_id)


async def open_prediction_window(match_id: str) -> None:
    """Open prediction window — set Redis key with TTL."""
    redis = get_redis()
    key = f"pred_window:{match_id}"
    await redis.setex(key, PREDICTION_WINDOW_SECONDS, "open")
    db = get_db()
    await db.matches.update_one(
        {"_id": match_id},
        {"$set": {"prediction_window_open": True}},
    )


async def close_prediction_window(match_id: str) -> None:
    """Close prediction window."""
    redis = get_redis()
    key = f"pred_window:{match_id}"
    await redis.delete(key)
    db = get_db()
    await db.matches.update_one(
        {"_id": match_id},
        {"$set": {"prediction_window_open": False}},
    )


async def is_prediction_window_open(match_id: str) -> bool:
    """Check if prediction window is currently open."""
    redis = get_redis()
    key = f"pred_window:{match_id}"
    return await redis.exists(key) == 1


async def get_cached_match_state(match_id: str) -> Optional[dict]:
    """Get match state from Redis cache (fast path for WebSocket/ML)."""
    redis = get_redis()
    cached = await redis.get(f"match_state:{match_id}")
    if cached:
        return json.loads(cached)

    match = await get_match(match_id)
    if match:
        await cache_match_state(match_id, match)
    return match


async def cache_match_state(match_id: str, match_data: dict) -> None:
    """Cache match state in Redis for fast access."""
    redis = get_redis()
    serializable = _make_serializable(match_data)
    await redis.setex(
        f"match_state:{match_id}",
        MATCH_CACHE_TTL,
        json.dumps(serializable),
    )


async def update_innings_score(
    match_id: str, innings: int, score: int, wickets: int, overs: float
) -> None:
    """Update innings score in the match document."""
    db = get_db()
    innings_key = f"innings.{innings - 1}"
    run_rate = round(score / overs, 2) if overs > 0 else 0.0

    await db.matches.update_one(
        {"_id": match_id},
        {
            "$set": {
                f"{innings_key}.score": score,
                f"{innings_key}.wickets": wickets,
                f"{innings_key}.overs": overs,
                f"{innings_key}.run_rate": run_rate,
                "updated_at": utc_now(),
            }
        },
    )
    await _invalidate_match_cache(match_id)


async def _invalidate_match_cache(match_id: str) -> None:
    redis = get_redis()
    await redis.delete(f"match_state:{match_id}")


def _make_serializable(obj):
    """Convert MongoDB doc to JSON-serializable dict."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj
