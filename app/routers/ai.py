from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.services import ml_service

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/match/{match_id}/probabilities")
async def get_probabilities(match_id: str):
    """Get AI ball outcome probabilities for a live match."""
    result = await ml_service.get_ball_probabilities(match_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/match/{match_id}/commentary")
async def get_commentary(match_id: str, limit: int = 10):
    """Get recent AI-generated commentary for a match."""
    db = get_db()
    cursor = db.ai_content.find(
        {"match_id": match_id, "type": {"$in": ["ball_commentary", "over_summary"]}},
    ).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"match_id": match_id, "commentary": items}
