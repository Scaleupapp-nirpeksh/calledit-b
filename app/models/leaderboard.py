from pydantic import BaseModel
from typing import Optional


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    total_points: int
    correct_predictions: int = 0
    accuracy: float = 0.0


class LeaderboardResponse(BaseModel):
    type: str  # "match", "daily", "season", "league"
    key: str   # match_id, date string, or league_id
    entries: list[LeaderboardEntry]
    total_participants: int
    my_rank: Optional[int] = None
    my_entry: Optional[LeaderboardEntry] = None
    neighbours: list[LeaderboardEntry] = []
    page: int = 1
    limit: int = 50
