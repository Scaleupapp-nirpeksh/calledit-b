"""Competition/Tournament service for CalledIt."""

import logging
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.utils.helpers import generate_nanoid, utc_now

logger = logging.getLogger(__name__)


async def create_competition(
    name: str,
    short_name: str,
    match_type: str = "T20",
    season: str = "",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    teams: Optional[list[str]] = None,
    is_platform_seeded: bool = True,
) -> dict:
    """Create a new competition."""
    db = get_db()
    now = utc_now()
    comp = {
        "_id": generate_nanoid(),
        "name": name,
        "short_name": short_name,
        "match_type": match_type,
        "season": season,
        "start_date": start_date,
        "end_date": end_date,
        "is_active": True,
        "is_platform_seeded": is_platform_seeded,
        "teams": teams or [],
        "match_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.competitions.insert_one(comp)
    logger.info(f"Competition created: {name} ({short_name})")
    return comp


async def get_competition(competition_id: str) -> Optional[dict]:
    """Get competition by ID."""
    db = get_db()
    return await db.competitions.find_one({"_id": competition_id})


async def get_competitions(
    is_active: Optional[bool] = None,
    season: Optional[str] = None,
) -> list[dict]:
    """List competitions with optional filters."""
    db = get_db()
    query: dict = {}
    if is_active is not None:
        query["is_active"] = is_active
    if season:
        query["season"] = season
    cursor = db.competitions.find(query).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def get_active_competitions() -> list[dict]:
    """Get currently active competitions."""
    return await get_competitions(is_active=True)


async def add_match_to_competition(competition_id: str, match_id: str) -> None:
    """Associate a match with a competition."""
    db = get_db()
    await db.matches.update_one(
        {"_id": match_id},
        {"$set": {"competition_id": competition_id}},
    )
    await db.competitions.update_one(
        {"_id": competition_id},
        {"$inc": {"match_count": 1}, "$set": {"updated_at": utc_now()}},
    )


async def get_competition_matches(competition_id: str) -> list[dict]:
    """Get all matches for a competition."""
    db = get_db()
    cursor = db.matches.find({"competition_id": competition_id}).sort("date", -1)
    return await cursor.to_list(length=200)


async def auto_assign_match_to_competition(match_doc: dict) -> Optional[str]:
    """Automatically assign a match to a competition based on teams and date.

    Returns competition_id if matched, None otherwise.
    """
    db = get_db()
    active_comps = await db.competitions.find({"is_active": True}).to_list(length=50)

    match_type = match_doc.get("match_type", "T20")
    team1 = match_doc.get("team1", "")
    team2 = match_doc.get("team2", "")

    for comp in active_comps:
        # Match type must match (case-insensitive)
        if comp.get("match_type", "T20").upper() != match_type.upper():
            continue

        comp_teams = comp.get("teams", [])

        # If competition has teams defined, both match teams must be in the list
        if comp_teams:
            if team1 not in comp_teams or team2 not in comp_teams:
                continue

        # If competition has date range, match date should fall within
        start = comp.get("start_date")
        end = comp.get("end_date")
        if start and end:
            match_date_str = match_doc.get("date", "")
            if match_date_str:
                try:
                    if isinstance(match_date_str, str):
                        match_date = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                    else:
                        match_date = match_date_str

                    if hasattr(start, "tzinfo") and start.tzinfo and not match_date.tzinfo:
                        match_date = match_date.replace(tzinfo=start.tzinfo)

                    if match_date < start or match_date > end:
                        continue
                except (ValueError, TypeError):
                    pass

        # Match found — assign
        await add_match_to_competition(comp["_id"], match_doc["_id"])
        logger.info(f"Match {match_doc['_id']} auto-assigned to {comp['name']}")
        return comp["_id"]

    return None
