from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.models.prediction import (
    BallPredictionRequest,
    MilestonePredictionRequest,
    MatchWinnerRequest,
    OverPredictionRequest,
)
from app.services import prediction_service
from app.utils.rate_limiter import rate_limit_predictions

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("/ball")
async def create_ball_prediction(
    body: BallPredictionRequest, user: dict = Depends(get_current_user)
):
    """Submit a ball-by-ball prediction."""
    await rate_limit_predictions(user["_id"])
    try:
        pred = await prediction_service.create_ball_prediction(
            user_id=user["_id"],
            match_id=body.match_id,
            innings=body.innings,
            over=body.over,
            ball=body.ball,
            prediction=body.prediction.value,
            confidence_boost=body.confidence_boost,
        )
        return {"prediction": pred}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/over")
async def create_over_prediction(
    body: OverPredictionRequest, user: dict = Depends(get_current_user)
):
    """Submit an over total prediction."""
    await rate_limit_predictions(user["_id"])
    try:
        pred = await prediction_service.create_over_prediction(
            user_id=user["_id"],
            match_id=body.match_id,
            innings=body.innings,
            over=body.over,
            predicted_runs=body.predicted_runs,
        )
        return {"prediction": pred}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/milestone")
async def create_milestone_prediction(
    body: MilestonePredictionRequest, user: dict = Depends(get_current_user)
):
    """Submit a milestone prediction."""
    await rate_limit_predictions(user["_id"])
    try:
        pred = await prediction_service.create_milestone_prediction(
            user_id=user["_id"],
            match_id=body.match_id,
            milestone_type=body.milestone_type,
            player_name=body.player_name,
            will_achieve=body.will_achieve,
        )
        return {"prediction": pred}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/match-winner")
async def create_match_winner_prediction(
    body: MatchWinnerRequest, user: dict = Depends(get_current_user)
):
    """Submit or update match winner prediction."""
    await rate_limit_predictions(user["_id"])
    try:
        pred = await prediction_service.create_match_winner_prediction(
            user_id=user["_id"],
            match_id=body.match_id,
            predicted_winner=body.predicted_winner,
        )
        return {"prediction": pred}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/match/{match_id}")
async def get_match_predictions(
    match_id: str, user: dict = Depends(get_current_user)
):
    """Get all predictions for a specific match by current user."""
    preds = await prediction_service.get_user_match_predictions(user["_id"], match_id)
    return {"predictions": preds, "total": len(preds)}


@router.get("/match/{match_id}/summary")
async def get_match_summary(
    match_id: str, user: dict = Depends(get_current_user)
):
    """Get prediction summary for a match."""
    summary = await prediction_service.get_user_match_summary(user["_id"], match_id)
    return summary


@router.get("/history")
async def get_prediction_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Get paginated prediction history."""
    preds, total = await prediction_service.get_prediction_history(
        user["_id"], page=page, limit=limit
    )
    return {"predictions": preds, "total": total, "page": page, "limit": limit}


@router.get("/stats")
async def get_prediction_stats(user: dict = Depends(get_current_user)):
    """Get overall prediction statistics."""
    stats = await prediction_service.get_prediction_stats(user["_id"])
    return stats
