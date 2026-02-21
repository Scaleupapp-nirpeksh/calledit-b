from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user
from app.services import image_service, match_service, prediction_service

router = APIRouter(prefix="/social", tags=["Social"])


@router.post("/share-card/{match_id}")
async def generate_share_card(
    match_id: str, user: dict = Depends(get_current_user)
):
    """Generate a shareable scorecard image for a match."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    summary = await prediction_service.get_user_match_summary(user["_id"], match_id)

    url = await image_service.generate_share_card(user, match, summary)

    # Store share record
    db = get_db()
    from app.utils.helpers import generate_nanoid, utc_now
    share_id = generate_nanoid(12)
    await db.shares.insert_one({
        "_id": share_id,
        "user_id": user["_id"],
        "match_id": match_id,
        "image_url": url,
        "created_at": utc_now(),
    })

    # Award badge
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"badges": "social_sharer"}},
    )

    return {"share_id": share_id, "image_url": url}


@router.get("/share/{share_id}")
async def get_share(share_id: str):
    """Get a shared scorecard by share ID (public endpoint for deep links)."""
    db = get_db()
    share = await db.shares.find_one({"_id": share_id})
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


@router.post("/referral/verify")
async def verify_referral(
    referral_code: str, user: dict = Depends(get_current_user)
):
    """Verify a referral code and link it to current user."""
    db = get_db()

    # Check if already referred
    if user.get("referred_by"):
        raise HTTPException(status_code=400, detail="Already used a referral code")

    referrer = await db.users.find_one({"referral_code": referral_code})
    if not referrer:
        raise HTTPException(status_code=404, detail="Invalid referral code")

    if referrer["_id"] == user["_id"]:
        raise HTTPException(status_code=400, detail="Cannot refer yourself")

    from app.utils.helpers import utc_now
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"referred_by": referrer["_id"], "updated_at": utc_now()}},
    )

    # Award referral badge to referrer
    await db.users.update_one(
        {"_id": referrer["_id"]},
        {"$addToSet": {"badges": "referral_1"}},
    )

    return {"message": "Referral applied successfully", "referrer": referrer.get("username")}
