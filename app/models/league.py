from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class CreateLeagueRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    competition_id: Optional[str] = None


class JoinLeagueRequest(BaseModel):
    invite_code: str = Field(..., min_length=6, max_length=10)


class LeagueMember(BaseModel):
    user_id: str
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    total_points: int = 0
    rank: Optional[int] = None
    joined_at: datetime


class LeagueResponse(BaseModel):
    id: str
    name: str
    invite_code: str
    owner_id: str
    competition_id: Optional[str] = None
    members: list[LeagueMember] = []
    member_count: int = 0
    max_members: int = 50
    created_at: datetime
    updated_at: datetime
