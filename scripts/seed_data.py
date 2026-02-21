"""CalledIt — Seed Data: IPL teams, admin user, competitions.

Usage: python -m scripts.seed_data
"""

import asyncio
import logging
import sys
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, ".")
from app.config import settings
from app.utils.constants import IPL_TEAMS
from app.utils.helpers import generate_nanoid, generate_referral_code, hash_phone, utc_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]
    now = utc_now()

    # ── Seed Admin User ──
    admin_phone = "+919999999999"
    admin_hash = hash_phone(admin_phone)
    existing_admin = await db.users.find_one({"phone_hash": admin_hash})

    if not existing_admin:
        admin_user = {
            "_id": generate_nanoid(),
            "phone_hash": admin_hash,
            "phone_encrypted": admin_phone,
            "username": "admin",
            "display_name": "CalledIt Admin",
            "avatar_url": None,
            "favourite_team": None,
            "favourite_players": [],
            "referral_code": generate_referral_code(),
            "referred_by": None,
            "is_onboarded": True,
            "is_admin": True,
            "stats": {
                "total_predictions": 0,
                "correct_predictions": 0,
                "accuracy": 0.0,
                "total_points": 0,
                "current_streak": 0,
                "best_streak": 0,
                "matches_played": 0,
                "clutch_correct": 0,
                "match_winners_correct": 0,
            },
            "badges": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(admin_user)
        logger.info(f"Admin user created: {admin_user['_id']}")
    else:
        logger.info("Admin user already exists")

    # ── Seed IPL Teams ──
    teams_collection = db.teams
    for code, name in IPL_TEAMS.items():
        existing = await teams_collection.find_one({"code": code})
        if not existing:
            await teams_collection.insert_one({
                "_id": code,
                "code": code,
                "name": name,
                "created_at": now,
            })
    logger.info(f"Seeded {len(IPL_TEAMS)} IPL teams")

    # ── Seed Competitions ──
    from datetime import datetime, timezone

    competitions = [
        {
            "_id": "comp_ipl_2026",
            "name": "Indian Premier League 2026",
            "short_name": "IPL",
            "match_type": "T20",
            "season": "2026",
            "start_date": datetime(2026, 3, 26, tzinfo=timezone.utc),
            "end_date": datetime(2026, 5, 25, tzinfo=timezone.utc),
            "is_active": True,
            "is_platform_seeded": True,
            "teams": list(IPL_TEAMS.values()),
            "match_count": 0,
            "created_at": now,
            "updated_at": now,
        },
        {
            "_id": "comp_t20wc_2026",
            "name": "ICC Men's T20 World Cup 2026",
            "short_name": "T20WC",
            "match_type": "T20",
            "season": "2026",
            "start_date": datetime(2026, 2, 9, tzinfo=timezone.utc),
            "end_date": datetime(2026, 3, 7, tzinfo=timezone.utc),
            "is_active": True,
            "is_platform_seeded": True,
            "teams": [
                "India", "Australia", "England", "South Africa",
                "New Zealand", "Pakistan", "West Indies", "Sri Lanka",
                "Bangladesh", "Afghanistan", "Zimbabwe", "Ireland",
                "Scotland", "Netherlands", "Namibia", "United States",
            ],
            "match_count": 0,
            "created_at": now,
            "updated_at": now,
        },
    ]

    for comp in competitions:
        existing = await db.competitions.find_one({"_id": comp["_id"]})
        if not existing:
            await db.competitions.insert_one(comp)
            logger.info(f"Competition created: {comp['name']}")
        else:
            logger.info(f"Competition already exists: {comp['name']}")

    logger.info("Seed data complete! Run 'POST /admin/matches/sync' to fetch real matches.")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
