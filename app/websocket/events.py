"""WebSocket Events — Socket.IO event handlers and emit helpers."""

import logging

from app.services.auth_service import _decode_token
from app.websocket.manager import sio

logger = logging.getLogger(__name__)


def register_events() -> None:
    """Register all Socket.IO event handlers."""

    @sio.event
    async def connect(sid, environ, auth):
        """Authenticate user on connect via JWT in auth dict."""
        token = None
        if auth and isinstance(auth, dict):
            token = auth.get("token")

        if not token:
            logger.warning(f"WS connect rejected (no token): {sid}")
            raise ConnectionRefusedError("Authentication required")

        try:
            payload = _decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                raise ValueError("No user ID in token")

            # Store user_id in session
            async with sio.session(sid) as session:
                session["user_id"] = user_id

            logger.info(f"WS connected: {sid} (user: {user_id})")
        except Exception as e:
            logger.warning(f"WS connect rejected (bad token): {sid} - {e}")
            raise ConnectionRefusedError("Invalid token")

    @sio.event
    async def disconnect(sid):
        logger.info(f"WS disconnected: {sid}")

    @sio.event
    async def join_match(sid, data):
        """Join a match room to receive live updates."""
        match_id = data.get("match_id") if isinstance(data, dict) else data
        if not match_id:
            return

        room = f"match:{match_id}"
        sio.enter_room(sid, room)

        async with sio.session(sid) as session:
            user_id = session.get("user_id", "unknown")

        logger.info(f"User {user_id} joined room {room}")

        # Send current match state
        from app.services.match_service import get_cached_match_state
        match_state = await get_cached_match_state(match_id)
        if match_state:
            await sio.emit("match_state", match_state, room=sid)

    @sio.event
    async def leave_match(sid, data):
        """Leave a match room."""
        match_id = data.get("match_id") if isinstance(data, dict) else data
        if not match_id:
            return
        room = f"match:{match_id}"
        sio.leave_room(sid, room)
        logger.info(f"SID {sid} left room {room}")


# ── Emit Helpers ──────────────────────────────────────────────────
# These are called by workers/services to push events to connected clients.

async def emit_ball_update(match_id: str, ball_data: dict) -> None:
    """Emit new ball result to all users in the match room."""
    await sio.emit("ball_update", ball_data, room=f"match:{match_id}")


async def emit_prediction_window(match_id: str, is_open: bool, ball_key: str = "") -> None:
    """Notify clients that prediction window opened/closed."""
    await sio.emit(
        "prediction_window",
        {"match_id": match_id, "is_open": is_open, "ball_key": ball_key},
        room=f"match:{match_id}",
    )


async def emit_score_update(match_id: str, score_data: dict) -> None:
    """Emit score/innings update."""
    await sio.emit("score_update", score_data, room=f"match:{match_id}")


async def emit_leaderboard_update(match_id: str, top_entries: list[dict]) -> None:
    """Emit updated leaderboard snapshot."""
    await sio.emit(
        "leaderboard_update",
        {"match_id": match_id, "entries": top_entries},
        room=f"match:{match_id}",
    )


async def emit_user_notification(user_sid: str, notification: dict) -> None:
    """Send notification to a specific user."""
    await sio.emit("notification", notification, room=user_sid)


async def emit_match_status_change(match_id: str, new_status: str) -> None:
    """Notify clients of match status change."""
    await sio.emit(
        "match_status",
        {"match_id": match_id, "status": new_status},
        room=f"match:{match_id}",
    )


async def emit_ai_commentary(match_id: str, commentary: str, ball_key: str) -> None:
    """Emit AI-generated ball commentary."""
    await sio.emit(
        "ai_commentary",
        {"match_id": match_id, "ball_key": ball_key, "commentary": commentary},
        room=f"match:{match_id}",
    )


async def emit_over_summary(match_id: str, innings: int, over: int, summary: str) -> None:
    """Emit AI-generated over summary."""
    await sio.emit(
        "over_summary",
        {"match_id": match_id, "innings": innings, "over": over, "summary": summary},
        room=f"match:{match_id}",
    )
