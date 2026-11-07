"""Persistence helpers for user reminders."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from prisma import Prisma


async def create_reminder(
    db: Prisma,
    *,
    user_id: str,
    guild_id: str | None,
    channel_id: str,
    message: str,
    remind_at: datetime,
) -> Any:
    return await db.reminder.create(
        data={
            "userId": user_id,
            "guildId": guild_id,
            "channelId": channel_id,
            "message": message,
            "remindAt": remind_at,
        }
    )


async def get_reminder(db: Prisma, user_id: str, reminder_id: str) -> Any | None:
    return await db.reminder.find_first(where={"id": reminder_id, "userId": user_id, "done": False})


async def list_pending_reminders(db: Prisma, user_id: str, *, limit: int = 25) -> list[Any]:
    return await db.reminder.find_many(
        where={"userId": user_id, "done": False},
        order={"remindAt": "asc"},
        take=max(1, min(limit, 100)),
    )


async def list_due_reminders(db: Prisma, *, limit: int = 100) -> list[Any]:
    return await db.reminder.find_many(
        where={"done": False, "remindAt": {"lte": datetime.now(timezone.utc)}},
        order={"remindAt": "asc"},
        take=max(1, min(limit, 500)),
    )


async def complete_reminder(db: Prisma, reminder_id: str) -> Any:
    return await db.reminder.update(where={"id": reminder_id}, data={"done": True})


async def delete_reminder(db: Prisma, user_id: str, reminder_id: str) -> Any | None:
    reminder = await get_reminder(db, user_id, reminder_id)
    if reminder is None:
        return None
    return await db.reminder.delete(where={"id": reminder.id})


async def delete_pending_reminders(db: Prisma, user_id: str) -> int:
    result = await db.reminder.delete_many(where={"userId": user_id, "done": False})
    return result if isinstance(result, int) else result.count


__all__ = [
    "complete_reminder",
    "create_reminder",
    "delete_pending_reminders",
    "delete_reminder",
    "get_reminder",
    "list_due_reminders",
    "list_pending_reminders",
]
