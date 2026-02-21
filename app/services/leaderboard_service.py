import logging
from datetime import date
from typing import Optional

from app.database import get_db
from app.redis_client import get_redis
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)


def _match_key(match_id: str) -> str:
    return f"lb:match:{match_id}"


def _daily_key(d: Optional[date] = None) -> str:
    d = d or utc_now().date()
    return f"lb:daily:{d.isoformat()}"


def _season_key() -> str:
    return "lb:season:2026"


def _league_key(league_id: str) -> str:
    return f"lb:league:{league_id}"


def _league_match_key(league_id: str, match_id: str) -> str:
    return f"lb:league:{league_id}:match:{match_id}"


def _competition_key(competition_id: str) -> str:
    return f"lb:competition:{competition_id}"


async def update_score(
    user_id: str,
    match_id: str,
    points: int,
    league_ids: list[str] | None = None,
    competition_id: str | None = None,
) -> None:
    """Increment user's score across all relevant leaderboards."""
    redis = get_redis()
    pipe = redis.pipeline()
    pipe.zincrby(_match_key(match_id), points, user_id)
    pipe.zincrby(_daily_key(), points, user_id)
    pipe.zincrby(_season_key(), points, user_id)

    if competition_id:
        pipe.zincrby(_competition_key(competition_id), points, user_id)

    for lid in (league_ids or []):
        pipe.zincrby(_league_key(lid), points, user_id)
        pipe.zincrby(_league_match_key(lid, match_id), points, user_id)

    await pipe.execute()


async def get_match_leaderboard(
    match_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    return await _get_leaderboard(_match_key(match_id), limit, offset)


async def get_daily_leaderboard(
    d: Optional[date] = None, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    return await _get_leaderboard(_daily_key(d), limit, offset)


async def get_season_leaderboard(
    limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    return await _get_leaderboard(_season_key(), limit, offset)


async def get_league_leaderboard(
    league_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    return await _get_leaderboard(_league_key(league_id), limit, offset)


async def get_league_match_leaderboard(
    league_id: str, match_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    return await _get_leaderboard(_league_match_key(league_id, match_id), limit, offset)


async def get_competition_leaderboard(
    competition_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    return await _get_leaderboard(_competition_key(competition_id), limit, offset)


async def get_user_rank(user_id: str, leaderboard_key: str) -> Optional[int]:
    """Get 1-indexed rank of user in a leaderboard."""
    redis = get_redis()
    rank = await redis.zrevrank(leaderboard_key, user_id)
    return (rank + 1) if rank is not None else None


async def get_user_neighbours(
    user_id: str, leaderboard_key: str, span: int = 2
) -> list[dict]:
    """Get ±span entries around the user in the leaderboard."""
    redis = get_redis()
    rank = await redis.zrevrank(leaderboard_key, user_id)
    if rank is None:
        return []

    start = max(0, rank - span)
    end = rank + span
    entries = await redis.zrevrange(leaderboard_key, start, end, withscores=True)

    db = get_db()
    result = []
    for idx, (uid, score) in enumerate(entries, start=start + 1):
        user = await db.users.find_one({"_id": uid}, {"username": 1, "display_name": 1, "avatar_url": 1})
        result.append({
            "rank": idx,
            "user_id": uid,
            "username": user.get("username", "") if user else "",
            "display_name": user.get("display_name") if user else None,
            "avatar_url": user.get("avatar_url") if user else None,
            "total_points": int(score),
        })
    return result


async def snapshot_to_mongodb(leaderboard_key: str, lb_type: str) -> None:
    """Save current leaderboard state to MongoDB for persistence."""
    redis = get_redis()
    entries = await redis.zrevrange(leaderboard_key, 0, -1, withscores=True)
    if not entries:
        return

    db = get_db()
    now = utc_now()
    snapshot = {
        "key": leaderboard_key,
        "type": lb_type,
        "entries": [
            {"rank": idx, "user_id": uid, "total_points": int(score)}
            for idx, (uid, score) in enumerate(entries, start=1)
        ],
        "total_participants": len(entries),
        "created_at": now,
    }
    await db.leaderboard_snapshots.insert_one(snapshot)
    logger.info(f"Snapshot saved: {leaderboard_key} ({len(entries)} entries)")


# ── Internal ──────────────────────────────────────────────────────

async def _get_leaderboard(
    key: str, limit: int, offset: int
) -> tuple[list[dict], int]:
    """Fetch leaderboard entries from Redis with user details from MongoDB."""
    redis = get_redis()
    total = await redis.zcard(key)
    entries_raw = await redis.zrevrange(key, offset, offset + limit - 1, withscores=True)

    db = get_db()
    entries = []
    for idx, (uid, score) in enumerate(entries_raw, start=offset + 1):
        user = await db.users.find_one(
            {"_id": uid},
            {"username": 1, "display_name": 1, "avatar_url": 1, "stats": 1},
        )
        entries.append({
            "rank": idx,
            "user_id": uid,
            "username": user.get("username", "") if user else "",
            "display_name": user.get("display_name") if user else None,
            "avatar_url": user.get("avatar_url") if user else None,
            "total_points": int(score),
            "correct_predictions": user.get("stats", {}).get("correct_predictions", 0) if user else 0,
            "accuracy": user.get("stats", {}).get("accuracy", 0.0) if user else 0.0,
        })

    return entries, total
