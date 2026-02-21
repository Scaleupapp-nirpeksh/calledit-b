"""CalledIt — MongoDB Migration: create indexes for all collections.

Usage: python -m scripts.migrate
"""

import asyncio
import logging
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

sys.path.insert(0, ".")
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_indexes():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]

    logger.info(f"Creating indexes on {settings.MONGODB_DB}...")

    # ── users ──
    await db.users.create_indexes([
        IndexModel([("phone_hash", ASCENDING)], unique=True),
        IndexModel([("username", ASCENDING)], unique=True, sparse=True),
        IndexModel([("referral_code", ASCENDING)], unique=True),
        IndexModel([("created_at", DESCENDING)]),
    ])
    logger.info("  users: 4 indexes")

    # ── matches ──
    await db.matches.create_indexes([
        IndexModel([("cricapi_id", ASCENDING)], unique=True, sparse=True),
        IndexModel([("status", ASCENDING), ("date", DESCENDING)]),
        IndexModel([("date", DESCENDING)]),
        IndexModel([("team1_code", ASCENDING)]),
        IndexModel([("team2_code", ASCENDING)]),
        IndexModel([("competition_id", ASCENDING)]),
    ])
    logger.info("  matches: 6 indexes")

    # ── predictions (critical for scoring queries) ──
    await db.predictions.create_indexes([
        IndexModel([("match_id", ASCENDING), ("ball_key", ASCENDING), ("type", ASCENDING), ("is_resolved", ASCENDING)]),
        IndexModel([("user_id", ASCENDING), ("match_id", ASCENDING), ("type", ASCENDING)]),
        IndexModel([("user_id", ASCENDING), ("match_id", ASCENDING), ("ball_key", ASCENDING), ("type", ASCENDING)], unique=True),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("match_id", ASCENDING), ("user_id", ASCENDING)]),
    ])
    logger.info("  predictions: 5 indexes")

    # ── leagues ──
    await db.leagues.create_indexes([
        IndexModel([("invite_code", ASCENDING)], unique=True),
        IndexModel([("members.user_id", ASCENDING)]),
        IndexModel([("owner_id", ASCENDING)]),
        IndexModel([("competition_id", ASCENDING)]),
    ])
    logger.info("  leagues: 4 indexes")

    # ── competitions ──
    await db.competitions.create_indexes([
        IndexModel([("short_name", ASCENDING), ("season", ASCENDING)], unique=True),
        IndexModel([("is_active", ASCENDING)]),
        IndexModel([("start_date", ASCENDING), ("end_date", ASCENDING)]),
    ])
    logger.info("  competitions: 3 indexes")

    # ── leaderboard_snapshots ──
    await db.leaderboard_snapshots.create_indexes([
        IndexModel([("key", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("type", ASCENDING), ("created_at", DESCENDING)]),
    ])
    logger.info("  leaderboard_snapshots: 2 indexes")

    # ── notifications (TTL: auto-delete after 30 days) ──
    await db.notifications.create_indexes([
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("user_id", ASCENDING), ("is_read", ASCENDING)]),
        IndexModel([("created_at", ASCENDING)], expireAfterSeconds=30 * 86400),
    ])
    logger.info("  notifications: 3 indexes (with 30-day TTL)")

    # ── ai_content ──
    await db.ai_content.create_indexes([
        IndexModel([("match_id", ASCENDING), ("type", ASCENDING), ("created_at", DESCENDING)]),
    ])
    logger.info("  ai_content: 1 index")

    # ── shares ──
    await db.shares.create_indexes([
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
    ])
    logger.info("  shares: 1 index")

    logger.info("All indexes created successfully!")
    client.close()


if __name__ == "__main__":
    asyncio.run(create_indexes())
