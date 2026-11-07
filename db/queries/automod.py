"""Persistent AutoMod configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


_ALLOWED_FIELDS = {
    "enabled",
    "antiSpam",
    "spamThreshold",
    "antiRaid",
    "raidThreshold",
    "filterEnabled",
    "filterWords",
    "capsEnabled",
    "capsThreshold",
    "linksEnabled",
    "mentionsEnabled",
    "mentionThreshold",
    "newAccountAge",
    "exemptRoles",
    "exemptChannels",
}


async def get_automod_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch one guild's AutoMod configuration."""
    return await db.automodconfig.find_unique(where={"guildId": guild_id})


async def upsert_automod_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Create or update supported AutoMod settings."""
    data = {key: value for key, value in changes.items() if key in _ALLOWED_FIELDS}
    await ensure_guild(db, guild_id)
    return await db.automodconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


__all__ = ["get_automod_config", "upsert_automod_config"]
