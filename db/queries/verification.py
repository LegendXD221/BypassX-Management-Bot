"""Persistent verification configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


_ALLOWED_FIELDS = {"enabled", "mode", "roleId", "channelId", "messageId"}


async def get_verify_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch one guild's verification configuration."""
    return await db.verifyconfig.find_unique(where={"guildId": guild_id})


async def upsert_verify_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Create or update supported verification settings."""
    data = {key: value for key, value in changes.items() if key in _ALLOWED_FIELDS}
    await ensure_guild(db, guild_id)
    return await db.verifyconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


__all__ = ["get_verify_config", "upsert_verify_config"]
