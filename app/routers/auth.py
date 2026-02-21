from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_current_user
from app.models.user import (
    AuthTokenResponse,
    RefreshTokenRequest,
    SendOTPRequest,
    VerifyOTPRequest,
)
from app.services import auth_service
from app.utils.rate_limiter import rate_limit_auth
from app.utils.validators import validate_phone

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/otp/send")
async def send_otp(body: SendOTPRequest, request: Request):
    """Send OTP to phone number for login/registration."""
    if not validate_phone(body.phone):
        raise HTTPException(status_code=400, detail="Invalid phone number. Use +91XXXXXXXXXX format.")

    await rate_limit_auth(request)

    try:
        result = await auth_service.send_otp(body.phone)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/otp/verify", response_model=AuthTokenResponse)
async def verify_otp(body: VerifyOTPRequest):
    """Verify OTP and get JWT tokens."""
    if not validate_phone(body.phone):
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    try:
        result = await auth_service.verify_otp(body.phone, body.otp)
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_token(body: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    try:
        result = await auth_service.refresh_tokens(body.refresh_token)
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout — revoke refresh token."""
    await auth_service.logout(user["_id"])
    return {"message": "Logged out successfully"}
