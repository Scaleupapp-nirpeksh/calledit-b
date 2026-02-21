"""CalledIt Backend — FastAPI Application Entry Point."""

import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_db, close_db
from app.redis_client import connect_redis, close_redis
from app.routers import auth, users, matches, predictions, leaderboards, leagues, social, ai, admin, competitions
from app.services.ml_service import initialize as init_ml
from app.websocket.events import register_events
from app.websocket.manager import sio

logging.basicConfig(
    level=logging.INFO if settings.is_dev else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    logger.info("CalledIt backend starting up...")
    await connect_db()
    await connect_redis()
    await init_ml()
    register_events()
    logger.info("CalledIt backend ready")

    yield

    # Shutdown
    logger.info("CalledIt backend shutting down...")
    await close_redis()
    await close_db()
    logger.info("CalledIt backend stopped")


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
