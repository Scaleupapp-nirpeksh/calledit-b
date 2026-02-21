from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.models.league import CreateLeagueRequest, JoinLeagueRequest
from app.services import league_service

router = APIRouter(prefix="/leagues", tags=["Leagues"])


@router.post("")
async def create_league(
    body: CreateLeagueRequest, user: dict = Depends(get_current_user)
):
    """Create a new private league."""
    league = await league_service.create_league(
        user["_id"], body.name, competition_id=body.competition_id
    )

    # Award league creator badge
    from app.database import get_db
    db = get_db()
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"badges": "league_creator"}},
    )

    return {"league": league}


@router.get("")
async def get_my_leagues(user: dict = Depends(get_current_user)):
    """Get all leagues the current user belongs to."""
    leagues = await league_service.get_user_leagues(user["_id"])
    return {"leagues": leagues, "total": len(leagues)}


@router.get("/{league_id}")
async def get_league(league_id: str):
    """Get league details."""
    league = await league_service.get_league(league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Enrich member data
    from app.database import get_db
    db = get_db()
    enriched_members = []
    for member in league.get("members", []):
        user = await db.users.find_one(
            {"_id": member["user_id"]},
            {"username": 1, "display_name": 1, "avatar_url": 1},
        )
        enriched_members.append({
            "user_id": member["user_id"],
            "username": user.get("username", "") if user else "",
            "display_name": user.get("display_name") if user else None,
            "avatar_url": user.get("avatar_url") if user else None,
            "joined_at": member.get("joined_at"),
        })
    league["members"] = enriched_members

    return {"league": league}


@router.post("/join")
async def join_league(
    body: JoinLeagueRequest, user: dict = Depends(get_current_user)
):
    """Join a league using invite code."""
    try:
        league = await league_service.join_league(user["_id"], body.invite_code)
        return {"league": league, "message": "Joined successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{league_id}/leave")
async def leave_league(league_id: str, user: dict = Depends(get_current_user)):
    """Leave a league."""
    try:
        await league_service.leave_league(user["_id"], league_id)
        return {"message": "Left league successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
