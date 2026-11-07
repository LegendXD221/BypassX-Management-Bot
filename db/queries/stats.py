"""Server statistics channel configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


STAT_TYPES = (
    "total_members",
    "online_members",
    "boosts",
    "channels",
    "roles",
    "bans",
)


async def list_stat_channels(db: Prisma, guild_id: str) -> list[Any]:
    """Return all configured live stat channels for a guild."""
    return await db.statchannel.find_many(where={"guildId": guild_id}, order={"type": "asc"})


async def get_stat_channel(db: Prisma, guild_id: str, stat_type: str) -> Any | None:
    """Fetch one configured stat channel."""
    return await db.statchannel.find_unique(where={"guildId_type": {"guildId": guild_id, "type": stat_type}})


async def upsert_stat_channel(db: Prisma, guild_id: str, stat_type: str, channel_id: str) -> Any:
    """Create or update a stat channel mapping."""
    if stat_type not in STAT_TYPES:
        raise ValueError(f"Unsupported stat type: {stat_type}")
    await ensure_guild(db, guild_id)
    return await db.statchannel.upsert(
        where={"guildId_type": {"guildId": guild_id, "type": stat_type}},
        data={
            "create": {"guildId": guild_id, "type": stat_type, "channelId": channel_id},
            "update": {"channelId": channel_id},
        },
    )


async def delete_stat_channels(db: Prisma, guild_id: str) -> int:
    """Remove all stat mappings for a guild."""
    result = await db.statchannel.delete_many(where={"guildId": guild_id})
    return result if isinstance(result, int) else result.count


__all__ = ["STAT_TYPES", "delete_stat_channels", "get_stat_channel", "list_stat_channels", "upsert_stat_channel"]
