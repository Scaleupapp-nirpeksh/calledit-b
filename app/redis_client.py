import logging
from redis.asyncio import Redis, from_url

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def connect_redis() -> None:
    global _redis
    logger.info("Connecting to Redis...")
    _redis = from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    # Verify connectivity
    await _redis.ping()
    logger.info("Redis connected successfully")


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Redis connection closed")


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call connect_redis() first.")
    return _redis
