"""Welcome, farewell, and autorole configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


_ALLOWED_FIELDS = {
    "welcomeChannel", "welcomeMessage", "welcomeCard",
    "farewellChannel", "farewellMessage", "autoRoles", "botAutoRoles",
}


async def get_welcome_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch the welcome configuration for a guild."""
    return await db.welcomeconfig.find_unique(where={"guildId": guild_id})


async def upsert_welcome_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Create or update supported welcome configuration fields."""
    data = {key: value for key, value in changes.items() if key in _ALLOWED_FIELDS}
    await ensure_guild(db, guild_id)
    return await db.welcomeconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


__all__ = ["get_welcome_config", "upsert_welcome_config"]
