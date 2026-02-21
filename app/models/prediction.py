from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

from app.utils.constants import BallOutcome, PredictionType


# --- Requests ---

class BallPredictionRequest(BaseModel):
    match_id: str
    innings: int = Field(..., ge=1, le=2)
    over: int = Field(..., ge=1, le=20)
    ball: int = Field(..., ge=1, le=8)  # up to 8 for extras
    prediction: BallOutcome
    confidence_boost: bool = False


class OverPredictionRequest(BaseModel):
    match_id: str
    innings: int = Field(..., ge=1, le=2)
    over: int = Field(..., ge=1, le=20)
    predicted_runs: int = Field(..., ge=0, le=50)


class MilestonePredictionRequest(BaseModel):
    match_id: str
    milestone_type: str  # e.g. "batter_50", "bowler_3w"
    player_name: str
    will_achieve: bool


class MatchWinnerRequest(BaseModel):
    match_id: str
    predicted_winner: str


# --- Responses ---

class PredictionResponse(BaseModel):
    id: str
    user_id: str
    match_id: str
    type: PredictionType
    innings: Optional[int] = None
    over: Optional[int] = None
    ball: Optional[int] = None
    ball_key: Optional[str] = None
    prediction: str
    confidence_boost: bool = False
    is_resolved: bool = False
    is_correct: Optional[bool] = None
    actual_outcome: Optional[str] = None
    base_points: int = 0
    streak_multiplier: float = 1.0
    confidence_multiplier: float = 1.0
    clutch_multiplier: float = 1.0
    total_points: int = 0
    created_at: datetime
    resolved_at: Optional[datetime] = None


class PredictionSummaryResponse(BaseModel):
    match_id: str
    user_id: str
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    total_points: int = 0
    current_streak: int = 0
    best_streak: int = 0
    confidence_boosts_used: int = 0
    confidence_boosts_remaining: int = 3
    predictions: list[PredictionResponse] = []


class PredictionHistoryResponse(BaseModel):
    predictions: list[PredictionResponse]
    total: int
    page: int
    limit: int


class PredictionStatsResponse(BaseModel):
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    total_points: int = 0
    best_streak: int = 0
    matches_played: int = 0
    by_type: dict[str, dict] = {}
