from fastapi import HTTPException, Request, status

from app.redis_client import get_redis


async def _check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """Generic Redis-based sliding window rate limiter."""
    redis = get_redis()
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    if current > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


async def rate_limit_auth(request: Request) -> None:
    """3 OTP requests per phone per 10 minutes."""
    body = await request.json()
    phone = body.get("phone", "unknown")
    key = f"rl:auth:{phone}"
    await _check_rate_limit(key, max_requests=3, window_seconds=600)


async def rate_limit_predictions(user_id: str) -> None:
    """120 predictions per user per minute."""
    key = f"rl:pred:{user_id}"
    await _check_rate_limit(key, max_requests=120, window_seconds=60)


async def rate_limit_general(request: Request) -> None:
    """60 requests per IP per minute."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"rl:gen:{client_ip}"
    await _check_rate_limit(key, max_requests=60, window_seconds=60)
