from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_admin
from app.services import cricket_data_service, match_service, ai_content_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/matches/sync")
async def sync_matches(
    admin: dict = Depends(get_current_admin),
):
    """Sync matches from all supported series (IPL + T20WC) via CricAPI."""
    results = await cricket_data_service.sync_all_supported_series()
    total = sum(results.values())
    return {"synced": total, "by_competition": results}


@router.post("/matches/enrich")
async def enrich_matches(
    admin: dict = Depends(get_current_admin),
):
    """Fetch scorecards, scores, team images for completed matches missing data."""
    enriched = await cricket_data_service.enrich_completed_matches()
    return {"enriched": enriched}


@router.post("/matches/{match_id}/status")
async def update_match_status(
    match_id: str, new_status: str, admin: dict = Depends(get_current_admin)
):
    """Manually update match status."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    await match_service.update_match_status(match_id, new_status)
    return {"message": f"Match status updated to {new_status}"}


@router.post("/ai/generate-preview/{match_id}")
async def generate_ai_preview(
    match_id: str, admin: dict = Depends(get_current_admin)
):
    """Manually trigger AI pre-match brief generation."""
    match = await match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    result = await ai_content_service.generate_pre_match_brief(match_id)
    return {"message": "AI preview generated", "content_id": result["_id"]}


@router.get("/stats/dashboard")
async def get_admin_dashboard(admin: dict = Depends(get_current_admin)):
    """Get admin dashboard statistics."""
    db = get_db()

    total_users = await db.users.count_documents({})
    total_predictions = await db.predictions.count_documents({})
    total_matches = await db.matches.count_documents({})
    live_matches = await db.matches.count_documents({"status": {"$in": ["live_1st", "live_2nd"]}})
    total_leagues = await db.leagues.count_documents({})

    # Recent stats
    from app.utils.helpers import utc_now
    from datetime import timedelta
    one_day_ago = utc_now() - timedelta(days=1)
    new_users_24h = await db.users.count_documents({"created_at": {"$gte": one_day_ago}})
    predictions_24h = await db.predictions.count_documents({"created_at": {"$gte": one_day_ago}})

    return {
        "total_users": total_users,
        "total_predictions": total_predictions,
        "total_matches": total_matches,
        "live_matches": live_matches,
        "total_leagues": total_leagues,
        "new_users_24h": new_users_24h,
        "predictions_24h": predictions_24h,
    }
