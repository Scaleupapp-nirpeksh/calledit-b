import logging
from typing import Optional

from app.database import get_db
from app.utils.constants import MAX_LEAGUE_MEMBERS
from app.utils.helpers import generate_nanoid, utc_now

logger = logging.getLogger(__name__)


async def create_league(
    user_id: str, name: str, competition_id: Optional[str] = None
) -> dict:
    """Create a new private league, optionally scoped to a competition."""
    db = get_db()
    now = utc_now()

    # Validate competition exists if provided
    if competition_id:
        comp = await db.competitions.find_one({"_id": competition_id})
        if not comp:
            raise ValueError("Competition not found")

    invite_code = generate_nanoid(8).upper()

    league_doc = {
        "_id": generate_nanoid(),
        "name": name,
        "invite_code": invite_code,
        "owner_id": user_id,
        "competition_id": competition_id,
        "members": [
            {
                "user_id": user_id,
                "joined_at": now,
            }
        ],
        "member_count": 1,
        "max_members": MAX_LEAGUE_MEMBERS,
        "created_at": now,
        "updated_at": now,
    }
    await db.leagues.insert_one(league_doc)
    return league_doc


async def join_league(user_id: str, invite_code: str) -> dict:
    """Join a league using an invite code."""
    db = get_db()
    league = await db.leagues.find_one({"invite_code": invite_code})
    if not league:
        raise ValueError("Invalid invite code")

    if league["member_count"] >= league["max_members"]:
        raise ValueError("League is full")

    for member in league["members"]:
        if member["user_id"] == user_id:
            raise ValueError("Already a member of this league")

    now = utc_now()
    await db.leagues.update_one(
        {"_id": league["_id"]},
        {
            "$push": {"members": {"user_id": user_id, "joined_at": now}},
            "$inc": {"member_count": 1},
            "$set": {"updated_at": now},
        },
    )

    league["member_count"] += 1
    return league


async def leave_league(user_id: str, league_id: str) -> None:
    """Leave a league. Owner cannot leave."""
    db = get_db()
    league = await db.leagues.find_one({"_id": league_id})
    if not league:
        raise ValueError("League not found")

    if league["owner_id"] == user_id:
        raise ValueError("League owner cannot leave. Transfer ownership or delete the league.")

    now = utc_now()
    await db.leagues.update_one(
        {"_id": league_id},
        {
            "$pull": {"members": {"user_id": user_id}},
            "$inc": {"member_count": -1},
            "$set": {"updated_at": now},
        },
    )


async def get_user_leagues(user_id: str) -> list[dict]:
    """Get all leagues the user is a member of."""
    db = get_db()
    cursor = db.leagues.find({"members.user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def get_league(league_id: str) -> Optional[dict]:
    """Get a single league by ID."""
    db = get_db()
    return await db.leagues.find_one({"_id": league_id})


async def get_user_league_ids(user_id: str) -> list[str]:
    """Get list of league IDs the user belongs to. Used by leaderboard service."""
    db = get_db()
    cursor = db.leagues.find(
        {"members.user_id": user_id},
        {"_id": 1},
    )
    leagues = await cursor.to_list(length=100)
    return [lg["_id"] for lg in leagues]
