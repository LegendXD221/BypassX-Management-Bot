"""Guild and per-guild configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma


async def ensure_guild(db: Prisma, guild_id: str) -> Any:
    """Create a guild root row if it does not exist and return it."""
    return await db.guild.upsert(
        where={"id": guild_id},
        data={"create": {"id": guild_id}, "update": {}},
    )


async def get_guild(db: Prisma, guild_id: str) -> Any | None:
    """Fetch a guild root row by Discord snowflake."""
    return await db.guild.find_unique(where={"id": guild_id})


async def update_guild(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Update supported root guild settings, creating the guild if needed."""
    allowed = {"prefix", "language"}
    data = {key: value for key, value in changes.items() if key in allowed}
    if not data:
        return await ensure_guild(db, guild_id)

    return await db.guild.upsert(
        where={"id": guild_id},
        data={"create": {"id": guild_id, **data}, "update": data},
    )


async def list_mod_tiers(db: Prisma, guild_id: str) -> list[Any]:
    """Return configured staff roles ordered from highest to lowest tier."""
    return await db.modtier.find_many(
        where={"guildId": guild_id},
        order={"tier": "desc"},
    )


async def upsert_mod_tier(db: Prisma, guild_id: str, role_id: str, tier: int) -> Any:
    """Assign a guild role to a permission tier."""
    await ensure_guild(db, guild_id)
    existing = await db.modtier.find_first(
        where={"guildId": guild_id, "roleId": role_id}
    )
    if existing:
        return await db.modtier.update(
            where={"id": existing.id},
            data={"tier": tier},
        )

    return await db.modtier.create(
        data={"guildId": guild_id, "roleId": role_id, "tier": tier}
    )


async def remove_mod_tier(db: Prisma, guild_id: str, role_id: str) -> int:
    """Remove a role's permission-tier assignment and return deleted count."""
    result = await db.modtier.delete_many(
        where={"guildId": guild_id, "roleId": role_id}
    )
    return result if isinstance(result, int) else result.count


async def reset_guild(db: Prisma, guild_id: str) -> None:
    """Remove the guild configuration and standalone guild-scoped records."""
    # These models intentionally do not all have a relation to Guild, so they
    # must be removed explicitly instead of relying on relational cascades.
    await db.modcase.delete_many(where={"guildId": guild_id})
    await db.warning.delete_many(where={"guildId": guild_id})
    await db.giveaway.delete_many(where={"guildId": guild_id})
    await db.reminder.delete_many(where={"guildId": guild_id})
    await db.cooldown.delete_many(where={"guildId": guild_id})
    await db.guild.delete_many(where={"id": guild_id})
