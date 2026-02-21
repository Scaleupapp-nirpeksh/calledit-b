from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.utils.constants import MatchStatus


class BallEntry(BaseModel):
    innings: int
    over: int
    ball: int
    ball_key: str
    batter: str
    bowler: str
    non_striker: str
    batter_runs: int
    extras: int = 0
    total_runs: int
    outcome: str  # BallOutcome value
    is_wicket: bool = False
    wicket_kind: Optional[str] = None
    player_out: Optional[str] = None
    commentary: Optional[str] = None
    timestamp: datetime


class InningsData(BaseModel):
    innings_number: int
    batting_team: str
    bowling_team: str
    score: int = 0
    wickets: int = 0
    overs: float = 0.0
    run_rate: float = 0.0
    target: Optional[int] = None  # only for 2nd innings
    required_rate: Optional[float] = None
    balls: list[BallEntry] = []


class MatchResponse(BaseModel):
    id: str
    cricapi_id: Optional[str] = None
    name: str
    match_type: str = "T20"
    status: MatchStatus
    venue: str
    date: datetime
    team1: str
    team2: str
    team1_code: str
    team2_code: str
    toss_winner: Optional[str] = None
    toss_decision: Optional[str] = None
    innings: list[InningsData] = []
    winner: Optional[str] = None
    result_text: Optional[str] = None
    competition_id: Optional[str] = None
    ai_preview: Optional[str] = None
    prediction_window_open: bool = False
    current_innings: Optional[int] = None
    current_over: Optional[int] = None
    current_ball: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class MatchListResponse(BaseModel):
    matches: list[MatchResponse]
    total: int


class MatchTimelineResponse(BaseModel):
    match_id: str
    innings: int
    balls: list[BallEntry]


class WinProbabilityEntry(BaseModel):
    ball_key: str
    team1_probability: float
    team2_probability: float
    timestamp: datetime


class WinProbabilityResponse(BaseModel):
    match_id: str
    team1: str
    team2: str
    current: Optional[WinProbabilityEntry] = None
    timeline: list[WinProbabilityEntry] = []
