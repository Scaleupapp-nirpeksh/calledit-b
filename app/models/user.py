from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


# --- Auth Requests ---

class SendOTPRequest(BaseModel):
    phone: str = Field(..., description="E.164 phone number (+91XXXXXXXXXX)")


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str = Field(..., min_length=6, max_length=6)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# --- Auth Responses ---

class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool = False


# --- User Profile ---

class UserStats(BaseModel):
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    total_points: int = 0
    current_streak: int = 0
    best_streak: int = 0
    matches_played: int = 0
    clutch_correct: int = 0
    match_winners_correct: int = 0


class UserResponse(BaseModel):
    id: str
    phone_masked: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    favourite_team: Optional[str] = None
    favourite_players: list[str] = []
    referral_code: str
    stats: UserStats = UserStats()
    badges: list[str] = []
    is_onboarded: bool = False
    created_at: datetime
    updated_at: datetime


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    favourite_team: Optional[str] = None
    favourite_players: Optional[list[str]] = None


class OnboardingRequest(BaseModel):
    username: str
    display_name: str
    favourite_team: Optional[str] = None
    favourite_players: list[str] = []
    referral_code_used: Optional[str] = None
