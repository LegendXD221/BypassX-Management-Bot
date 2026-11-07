"""Persistence helpers for the giveaway system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


async def create_giveaway(
    db: Prisma,
    guild_id: str,
    *,
    channel_id: str,
    message_id: str,
    prize: str,
    winners_count: int,
    ends_at: datetime,
    giveaway_id: str | None = None,
) -> Any:
    await ensure_guild(db, guild_id)
    data: dict[str, Any] = {
        "guildId": guild_id,
        "channelId": channel_id,
        "messageId": message_id,
        "prize": prize,
        "winnersCount": winners_count,
        "endsAt": ends_at,
    }
    if giveaway_id:
        data["id"] = giveaway_id
    return await db.giveaway.create(data=data)


async def get_giveaway(db: Prisma, guild_id: str, giveaway_id: str) -> Any | None:
    return await db.giveaway.find_first(where={"id": giveaway_id, "guildId": guild_id})


async def list_active_giveaways(db: Prisma, guild_id: str) -> list[Any]:
    return await db.giveaway.find_many(
        where={"guildId": guild_id, "ended": False},
        order={"endsAt": "asc"},
    )


async def list_due_giveaways(db: Prisma) -> list[Any]:
    return await db.giveaway.find_many(
        where={"ended": False, "paused": False, "endsAt": {"lte": datetime.now(timezone.utc)}},
        take=100,
    )


async def list_finished_giveaways(db: Prisma, guild_id: str, limit: int = 50) -> list[Any]:
    return await db.giveaway.find_many(
        where={"guildId": guild_id, "ended": True},
        order={"endsAt": "desc"},
        take=max(1, min(limit, 100)),
    )


async def add_entry(db: Prisma, giveaway_id: str, user_id: str) -> tuple[Any, bool]:
    giveaway = await db.giveaway.find_unique(where={"id": giveaway_id})
    if giveaway is None:
        raise ValueError("Giveaway not found")
    entries = list(giveaway.entries or [])
    if user_id in entries:
        return giveaway, False
    entries.append(user_id)
    return await db.giveaway.update(where={"id": giveaway_id}, data={"entries": entries}), True


async def update_giveaway(db: Prisma, giveaway_id: str, **changes: Any) -> Any:
    allowed = {"prize", "endsAt", "winnersCount", "paused", "ended", "winners", "messageId"}
    data = {key: value for key, value in changes.items() if key in allowed}
    return await db.giveaway.update(where={"id": giveaway_id}, data=data)


async def delete_giveaway(db: Prisma, giveaway_id: str) -> Any:
    return await db.giveaway.delete(where={"id": giveaway_id})


__all__ = [
    "add_entry",
    "create_giveaway",
    "delete_giveaway",
    "get_giveaway",
    "list_active_giveaways",
    "list_due_giveaways",
    "list_finished_giveaways",
    "update_giveaway",
]
