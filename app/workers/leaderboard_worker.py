"""Leaderboard Worker — periodic tasks for leaderboard maintenance."""

import logging
from datetime import date, timedelta

from app.services.leaderboard_service import (
    _daily_key,
    _season_key,
    snapshot_to_mongodb,
)
from app.redis_client import get_redis

logger = logging.getLogger(__name__)


async def snapshot_daily_leaderboard(d: date | None = None) -> None:
    """Snapshot today's daily leaderboard to MongoDB (run at end of day)."""
    d = d or date.today()
    key = _daily_key(d)
    await snapshot_to_mongodb(key, "daily")
    logger.info(f"Daily leaderboard snapshot saved: {d.isoformat()}")


async def rebuild_season_leaderboard() -> None:
    """Safety rebuild: recalculate season leaderboard from MongoDB predictions.
    This is a fallback in case Redis data is lost.
    """
    from app.database import get_db

    db = get_db()
    redis = get_redis()
    season_key = _season_key()

    # Clear existing
    await redis.delete(season_key)

    # Aggregate total points per user from predictions
    pipeline = [
        {"$match": {"is_resolved": True}},
        {"$group": {"_id": "$user_id", "total_points": {"$sum": "$total_points"}}},
    ]
    results = await db.predictions.aggregate(pipeline).to_list(length=100000)

    if results:
        pipe = redis.pipeline()
        for r in results:
            if r["total_points"] > 0:
                pipe.zadd(season_key, {r["_id"]: r["total_points"]})
        await pipe.execute()

    logger.info(f"Season leaderboard rebuilt: {len(results)} users")


async def prune_old_leaderboards(days_to_keep: int = 30) -> None:
    """Delete old daily leaderboard keys from Redis."""
    redis = get_redis()
    today = date.today()

    pruned = 0
    for i in range(days_to_keep + 1, days_to_keep + 90):
        old_date = today - timedelta(days=i)
        key = _daily_key(old_date)
        deleted = await redis.delete(key)
        pruned += deleted

    if pruned:
        logger.info(f"Pruned {pruned} old daily leaderboard keys")
