"""WebSocket Manager — Socket.IO server with Redis adapter for production."""

import logging

import socketio

from app.config import settings

logger = logging.getLogger(__name__)

# Create Socket.IO server
if settings.is_dev:
    # In-memory for development
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins=settings.allowed_origins_list or "*",
        logger=False,
        engineio_logger=False,
    )
else:
    # Redis adapter for production (multi-worker support)
    mgr = socketio.AsyncRedisManager(settings.REDIS_URL)
    sio = socketio.AsyncServer(
        async_mode="asgi",
        client_manager=mgr,
        cors_allowed_origins=settings.allowed_origins_list or "*",
        logger=False,
        engineio_logger=False,
    )

logger.info(f"Socket.IO server created (mode: {'dev' if settings.is_dev else 'production'})")
