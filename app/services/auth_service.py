import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from twilio.rest import Client as TwilioClient

from app.config import settings
from app.database import get_db
from app.redis_client import get_redis
from app.utils.helpers import generate_nanoid, generate_referral_code, hash_phone, utc_now

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"


def _get_twilio_client() -> TwilioClient:
    return TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def send_otp(phone: str) -> dict:
    """Generate 6-digit OTP, store in Redis (5min TTL), send via Twilio."""
    otp = f"{secrets.randbelow(900000) + 100000}"
    redis = get_redis()
    otp_key = f"otp:{hash_phone(phone)}"

    # Store OTP with 5-minute TTL
    await redis.setex(otp_key, 300, otp)

    if settings.is_dev:
        logger.info(f"[DEV] OTP for {phone}: {otp}")
    else:
        client = _get_twilio_client()
        client.messages.create(
            body=f"Your CalledIt verification code is: {otp}",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone,
        )

    result = {"message": "OTP sent successfully"}
    if settings.is_dev:
        result["otp"] = otp  # Dev only — never in production
    return result


async def verify_otp(phone: str, otp: str) -> dict:
    """Validate OTP, create user if new, return JWT pair."""
    redis = get_redis()
    otp_key = f"otp:{hash_phone(phone)}"

    stored_otp = await redis.get(otp_key)
    if not stored_otp or stored_otp != otp:
        raise ValueError("Invalid or expired OTP")

    # Delete OTP after successful verification
    await redis.delete(otp_key)

    db = get_db()
    phone_hash = hash_phone(phone)
    user = await db.users.find_one({"phone_hash": phone_hash})

    is_new_user = False
    if not user:
        is_new_user = True
        user_id = generate_nanoid()
        now = utc_now()
        user = {
            "_id": user_id,
            "phone_hash": phone_hash,
            "phone_encrypted": phone,  # TODO: encrypt with AES in production
            "username": None,
            "display_name": None,
            "avatar_url": None,
            "favourite_team": None,
            "favourite_players": [],
            "referral_code": generate_referral_code(),
            "referred_by": None,
            "is_onboarded": False,
            "is_admin": False,
            "stats": {
                "total_predictions": 0,
                "correct_predictions": 0,
                "accuracy": 0.0,
                "total_points": 0,
                "current_streak": 0,
                "best_streak": 0,
                "matches_played": 0,
                "clutch_correct": 0,
                "match_winners_correct": 0,
            },
            "badges": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(user)

    user_id = user["_id"]
    access_token = _create_access_token(user_id)
    refresh_token = _create_refresh_token(user_id)

    # Store refresh token in Redis for revocation support
    refresh_key = f"refresh:{user_id}"
    await redis.setex(
        refresh_key,
        settings.JWT_REFRESH_EXPIRE_DAYS * 86400,
        refresh_token,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        "is_new_user": is_new_user,
    }


async def refresh_tokens(refresh_token: str) -> dict:
    """Validate refresh token and issue new pair."""
    payload = _decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type")

    user_id = payload["sub"]
    redis = get_redis()

    # Verify refresh token is still valid in Redis
    stored = await redis.get(f"refresh:{user_id}")
    if not stored or stored != refresh_token:
        raise ValueError("Refresh token revoked or expired")

    # Issue new pair
    new_access = _create_access_token(user_id)
    new_refresh = _create_refresh_token(user_id)

    # Replace old refresh token
    await redis.setex(
        f"refresh:{user_id}",
        settings.JWT_REFRESH_EXPIRE_DAYS * 86400,
        new_refresh,
    )

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        "is_new_user": False,
    }


async def logout(user_id: str) -> None:
    """Revoke refresh token."""
    redis = get_redis()
    await redis.delete(f"refresh:{user_id}")


def _create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "type": "access", "exp": expire},
        settings.APP_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        settings.APP_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.APP_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
