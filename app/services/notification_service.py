import logging
from typing import Optional

from app.database import get_db
from app.utils.helpers import generate_nanoid, utc_now

logger = logging.getLogger(__name__)


async def create_notification(
    user_id: str,
    type: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> dict:
    """Create an in-app notification."""
    db = get_db()
    now = utc_now()
    notif = {
        "_id": generate_nanoid(),
        "user_id": user_id,
        "type": type,
        "title": title,
        "body": body,
        "data": data or {},
        "is_read": False,
        "created_at": now,
    }
    await db.notifications.insert_one(notif)
    return notif


async def get_user_notifications(
    user_id: str, page: int = 1, limit: int = 20
) -> tuple[list[dict], int, int]:
    """Get paginated notifications. Returns (notifications, total, unread_count)."""
    db = get_db()
    query = {"user_id": user_id}
    total = await db.notifications.count_documents(query)
    unread = await db.notifications.count_documents({**query, "is_read": False})
    offset = (page - 1) * limit
    cursor = db.notifications.find(query).sort("created_at", -1).skip(offset).limit(limit)
    notifs = await cursor.to_list(length=limit)
    return notifs, total, unread


async def mark_read(notification_id: str) -> None:
    """Mark a single notification as read."""
    db = get_db()
    await db.notifications.update_one(
        {"_id": notification_id},
        {"$set": {"is_read": True}},
    )


async def mark_all_read(user_id: str) -> int:
    """Mark all notifications as read for a user. Returns count modified."""
    db = get_db()
    result = await db.notifications.update_many(
        {"user_id": user_id, "is_read": False},
        {"$set": {"is_read": True}},
    )
    return result.modified_count


async def get_unread_count(user_id: str) -> int:
    """Get count of unread notifications."""
    db = get_db()
    return await db.notifications.count_documents({"user_id": user_id, "is_read": False})
