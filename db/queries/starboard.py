"""Persistence helpers for starboard and engagement analytics."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild

STARBOARD_FIELDS = {
    "enabled",
    "channelId",
    "threshold",
    "emoji",
    "allowSelfStar",
    "ignoredChannels",
}


async def get_starboard_config(db: Prisma, guild_id: str) -> Any | None:
    return await db.starboardconfig.find_unique(where={"guildId": guild_id})


async def upsert_starboard_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    data = {key: value for key, value in changes.items() if key in STARBOARD_FIELDS}
    await ensure_guild(db, guild_id)
    return await db.starboardconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


async def get_starboard_message(db: Prisma, guild_id: str, source_message_id: str) -> Any | None:
    return await db.starboardmessage.find_unique(
        where={"guildId_sourceMessageId": {"guildId": guild_id, "sourceMessageId": source_message_id}}
    )


async def upsert_starboard_message(db: Prisma, guild_id: str, source_message_id: str, **data: Any) -> Any:
    allowed = {
        "sourceChannelId", "starboardMessageId", "authorId", "content",
        "attachmentUrls", "stars",
    }
    payload = {key: value for key, value in data.items() if key in allowed}
    return await db.starboardmessage.upsert(
        where={"guildId_sourceMessageId": {"guildId": guild_id, "sourceMessageId": source_message_id}},
        data={
            "create": {"guildId": guild_id, "sourceMessageId": source_message_id, **payload},
            "update": payload,
        },
    )


async def set_starboard_message_id(db: Prisma, record_id: str, message_id: str) -> Any:
    return await db.starboardmessage.update(
        where={"id": record_id},
        data={"starboardMessageId": message_id},
    )


async def update_star_count(db: Prisma, record_id: str, stars: int) -> Any:
    return await db.starboardmessage.update(
        where={"id": record_id},
        data={"stars": max(0, stars)},
    )


async def top_starboard_messages(db: Prisma, guild_id: str, limit: int = 10) -> list[Any]:
    return await db.starboardmessage.find_many(
        where={"guildId": guild_id},
        order={"stars": "desc"},
        take=max(1, min(limit, 50)),
    )


async def increment_engagement(
    db: Prisma,
    guild_id: str,
    *,
    day: str,
    field: str,
    amount: int = 1,
) -> Any:
    if field not in {"messages", "reactions", "joins", "leaves", "activeUsers"}:
        raise ValueError(f"Unsupported engagement field: {field}")
    await ensure_guild(db, guild_id)
    return await db.engagementdaily.upsert(
        where={"guildId_date": {"guildId": guild_id, "date": day}},
        data={
            "create": {"guildId": guild_id, "date": day, field: max(0, amount)},
            "update": {field: {"increment": amount}},
        },
    )


async def list_engagement_days(db: Prisma, guild_id: str, days: int = 7) -> list[Any]:
    """Return recent daily rows; PostgreSQL date strings sort lexicographically."""
    days = max(1, min(days, 31))
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    return await db.engagementdaily.find_many(
        where={"guildId": guild_id, "date": {"gte": start}},
        order={"date": "asc"},
    )


__all__ = [
    "STARBOARD_FIELDS",
    "get_starboard_config",
    "get_starboard_message",
    "increment_engagement",
    "list_engagement_days",
    "set_starboard_message_id",
    "top_starboard_messages",
    "update_star_count",
    "upsert_starboard_config",
    "upsert_starboard_message",
]
