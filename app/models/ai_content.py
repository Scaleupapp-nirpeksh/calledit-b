from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class AIContentResponse(BaseModel):
    id: str
    match_id: str
    type: str  # "pre_match_brief", "post_match_report", "over_summary"
    content: str
    model_used: str
    tokens_used: int = 0
    generation_time_ms: int = 0
    created_at: datetime


class AIProbabilitiesResponse(BaseModel):
    match_id: str
    ball_key: Optional[str] = None
    probabilities: dict[str, float]  # {"dot": 0.35, "1": 0.25, ...}
    model_version: str = "v1"
    generated_at: datetime


class CommentaryResponse(BaseModel):
    match_id: str
    ball_key: str
    commentary: str
    is_ai_generated: bool = True
    generated_at: datetime
