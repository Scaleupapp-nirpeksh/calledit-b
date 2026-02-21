"""CalledIt Backend — FastAPI Application Entry Point."""

import asyncio
import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_db, close_db
from app.redis_client import connect_redis, get_redis, close_redis
from app.routers import auth, users, matches, predictions, leaderboards, leagues, social, ai, admin, competitions
from app.services.ml_service import initialize as init_ml
from app.websocket.events import register_events
from app.websocket.manager import sio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_poller_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown lifecycle."""
    global _poller_task

    # Startup
    logger.info("CalledIt backend starting up...")
    await connect_db()
    await connect_redis()
    await init_ml()
    register_events()

    # Start cricket poller (Redis lock ensures only one worker runs it)
    _poller_task = asyncio.create_task(_run_poller_with_lock())

    logger.info("CalledIt backend ready")

    yield

    # Shutdown
    logger.info("CalledIt backend shutting down...")
    if _poller_task:
        _poller_task.cancel()
        try:
            await _poller_task
        except asyncio.CancelledError:
            pass
    await close_redis()
    await close_db()
    logger.info("CalledIt backend stopped")


async def _run_poller_with_lock():
    """Acquire a Redis lock so only one worker runs the cricket poller."""
    from app.workers.cricket_poller import start_poller, stop_poller

    redis = get_redis()
    lock_key = "calledit:poller_lock"

    # Try to acquire lock (expires after 30s, renewed every cycle)
    acquired = await redis.set(lock_key, "1", nx=True, ex=30)
    if not acquired:
        logger.info("Another worker owns the poller lock — skipping")
        return

    logger.info("Poller lock acquired — starting cricket poller")
    try:
        # Keep renewing the lock while polling
        async def _renew_lock():
            while True:
                await redis.expire(lock_key, 30)
                await asyncio.sleep(10)

        renew_task = asyncio.create_task(_renew_lock())
        await start_poller()
    except asyncio.CancelledError:
        stop_poller()
        renew_task.cancel()
    finally:
        await redis.delete(lock_key)


# Create FastAPI app
app = FastAPI(
    title="CalledIt API",
    description="Real-time cricket prediction game backend",
    version="1.0.0",
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers under /api/v1
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(matches.router, prefix="/api/v1")
app.include_router(predictions.router, prefix="/api/v1")
app.include_router(leaderboards.router, prefix="/api/v1")
app.include_router(leagues.router, prefix="/api/v1")
app.include_router(social.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(competitions.router, prefix="/api/v1")


# Health check
@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "service": "calledit-backend", "version": "1.0.0"}


# Wrap FastAPI with Socket.IO ASGI app
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
