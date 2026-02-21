from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str  # "prediction_result", "streak", "badge", "league", "match_start", etc.
    title: str
    body: str
    data: Optional[dict] = None
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    limit: int
