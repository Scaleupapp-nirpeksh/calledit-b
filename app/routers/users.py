from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import OnboardingRequest, UpdateProfileRequest
from app.utils.helpers import mask_phone, utc_now
from app.utils.validators import validate_username

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user's profile."""
    return _format_user(user)


@router.patch("/me")
async def update_profile(
    body: UpdateProfileRequest, user: dict = Depends(get_current_user)
):
    """Update current user's profile."""
    db = get_db()
    update = {}

    if body.username is not None:
        if not validate_username(body.username):
            raise HTTPException(status_code=400, detail="Invalid username. 3-20 chars, alphanumeric + underscore.")
        # Check uniqueness
        existing = await db.users.find_one({"username": body.username, "_id": {"$ne": user["_id"]}})
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken.")
        update["username"] = body.username

    if body.display_name is not None:
        update["display_name"] = body.display_name
    if body.avatar_url is not None:
        update["avatar_url"] = body.avatar_url
    if body.favourite_team is not None:
        update["favourite_team"] = body.favourite_team
    if body.favourite_players is not None:
        update["favourite_players"] = body.favourite_players

    if update:
        update["updated_at"] = utc_now()
        await db.users.update_one({"_id": user["_id"]}, {"$set": update})

    updated = await db.users.find_one({"_id": user["_id"]})
    return _format_user(updated)


@router.post("/me/onboarding")
async def complete_onboarding(
    body: OnboardingRequest, user: dict = Depends(get_current_user)
):
    """Complete user onboarding (set username, display name, preferences)."""
    db = get_db()

    if not validate_username(body.username):
        raise HTTPException(status_code=400, detail="Invalid username.")

    existing = await db.users.find_one({"username": body.username, "_id": {"$ne": user["_id"]}})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken.")

    update = {
        "username": body.username,
        "display_name": body.display_name,
        "favourite_team": body.favourite_team,
        "favourite_players": body.favourite_players,
        "is_onboarded": True,
        "updated_at": utc_now(),
    }

    # Handle referral code
    if body.referral_code_used:
        referrer = await db.users.find_one({"referral_code": body.referral_code_used})
        if referrer:
            update["referred_by"] = referrer["_id"]
            # Award referral badge to referrer
            await db.users.update_one(
                {"_id": referrer["_id"]},
                {"$addToSet": {"badges": "referral_1"}},
            )

    await db.users.update_one({"_id": user["_id"]}, {"$set": update})
    updated = await db.users.find_one({"_id": user["_id"]})
    return _format_user(updated)


@router.get("/{user_id}")
async def get_user(user_id: str):
    """Get a user's public profile."""
    db = get_db()
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _format_user(user)


@router.get("/{user_id}/predictions")
async def get_user_predictions(user_id: str, match_id: str | None = None):
    """Get a user's prediction history."""
    from app.services.prediction_service import get_prediction_history, get_user_match_predictions

    if match_id:
        preds = await get_user_match_predictions(user_id, match_id)
        return {"predictions": preds, "total": len(preds)}

    preds, total = await get_prediction_history(user_id)
    return {"predictions": preds, "total": total}


def _format_user(user: dict) -> dict:
    """Format user dict for API response."""
    return {
        "id": user["_id"],
        "phone_masked": mask_phone(user.get("phone_encrypted", "")),
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "avatar_url": user.get("avatar_url"),
        "favourite_team": user.get("favourite_team"),
        "favourite_players": user.get("favourite_players", []),
        "referral_code": user.get("referral_code", ""),
        "stats": user.get("stats", {}),
        "badges": user.get("badges", []),
        "is_onboarded": user.get("is_onboarded", False),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }
