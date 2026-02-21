"""Pydantic models for competitions/tournaments."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateCompetitionRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    short_name: str = Field(..., min_length=2, max_length=20)
    match_type: str = "T20"
    season: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    teams: list[str] = []


class CompetitionResponse(BaseModel):
    id: str
    name: str
    short_name: str
    match_type: str
    season: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    is_platform_seeded: bool = True
    teams: list[str] = []
    match_count: int = 0
    created_at: datetime
    updated_at: datetime


class CompetitionListResponse(BaseModel):
    competitions: list[CompetitionResponse]
    total: int
