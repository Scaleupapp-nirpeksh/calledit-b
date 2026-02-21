"""Tests for CalledIt auth flow — OTP, JWT, rate limiting."""

import pytest

from app.services.auth_service import (
    _create_access_token,
    _create_refresh_token,
    _decode_token,
    send_otp,
    verify_otp,
)


class TestJWT:
    def test_create_and_decode_access_token(self):
        token = _create_access_token("user_123")
        payload = _decode_token(token)
        assert payload["sub"] == "user_123"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self):
        token = _create_refresh_token("user_123")
        payload = _decode_token(token)
        assert payload["sub"] == "user_123"
        assert payload["type"] == "refresh"

    def test_invalid_token(self):
        with pytest.raises(ValueError, match="Invalid token"):
            _decode_token("invalid.token.here")


@pytest.mark.asyncio
class TestOTPFlow:
    async def test_send_otp(self, setup_redis):
        result = await send_otp("+919876543210")
        assert result["message"] == "OTP sent successfully"

    async def test_verify_otp_creates_new_user(self, setup_db, setup_redis):
        # Send OTP first
        await send_otp("+919876543210")

        # Get OTP from Redis
        from app.utils.helpers import hash_phone
        otp = await setup_redis.get(f"otp:{hash_phone('+919876543210')}")
        assert otp is not None

        # Verify
        result = await verify_otp("+919876543210", otp)
        assert result["access_token"]
        assert result["refresh_token"]
        assert result["is_new_user"] is True

    async def test_verify_otp_existing_user(self, setup_db, setup_redis, test_user):
        phone = "+919876543210"
        await send_otp(phone)

        from app.utils.helpers import hash_phone
        otp = await setup_redis.get(f"otp:{hash_phone(phone)}")

        result = await verify_otp(phone, otp)
        assert result["access_token"]
        assert result["is_new_user"] is False

    async def test_verify_wrong_otp(self, setup_db, setup_redis):
        await send_otp("+919876543210")
        with pytest.raises(ValueError, match="Invalid or expired OTP"):
            await verify_otp("+919876543210", "000000")

    async def test_otp_expires(self, setup_redis):
        from app.utils.helpers import hash_phone
        key = f"otp:{hash_phone('+919876543210')}"
        ttl = await setup_redis.ttl(key)
        # OTP should not exist before send
        assert ttl <= 0

        await send_otp("+919876543210")
        ttl = await setup_redis.ttl(key)
        assert 0 < ttl <= 300  # 5 minutes
