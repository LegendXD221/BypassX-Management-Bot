"""Leveling configuration, XP, and reward queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


async def get_or_create_level(db: Prisma, guild_id: str, user_id: str) -> Any:
    """Return a member's level record, creating the default row when needed."""
    return await db.memberlevel.upsert(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={"create": {"guildId": guild_id, "userId": user_id}, "update": {}},
    )


async def add_xp(db: Prisma, guild_id: str, user_id: str, amount: int) -> Any:
    """Atomically add XP to a persistent level record."""
    if amount < 0:
        raise ValueError("XP amount cannot be negative")
    await get_or_create_level(db, guild_id, user_id)
    return await db.memberlevel.update(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={"xp": {"increment": amount}},
    )


async def set_xp(db: Prisma, guild_id: str, user_id: str, xp: int) -> Any:
    """Set a member's XP, rejecting negative values."""
    if xp < 0:
        raise ValueError("XP cannot be negative")
    await get_or_create_level(db, guild_id, user_id)
    return await db.memberlevel.update(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={"xp": xp},
    )


async def set_level(db: Prisma, guild_id: str, user_id: str, level: int) -> Any:
    """Set a member's current level, rejecting invalid negative levels."""
    if level < 0:
        raise ValueError("Level cannot be negative")
    await get_or_create_level(db, guild_id, user_id)
    return await db.memberlevel.update(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={"level": level},
    )


async def reset_level(db: Prisma, guild_id: str, user_id: str) -> Any:
    """Reset a member's XP and level to zero."""
    await get_or_create_level(db, guild_id, user_id)
    return await db.memberlevel.update(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={"xp": 0, "level": 0},
    )


async def leaderboard(db: Prisma, guild_id: str, limit: int = 100) -> list[Any]:
    """Return the highest-XP members for a guild."""
    return await db.memberlevel.find_many(
        where={"guildId": guild_id},
        order={"xp": "desc"},
        take=max(1, min(limit, 100)),
    )


async def get_level_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch the leveling configuration for a guild."""
    return await db.levelconfig.find_unique(where={"guildId": guild_id})


async def upsert_level_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Create or update supported leveling settings."""
    allowed = {
        "enabled", "xpMin", "xpMax", "cooldown", "announceEnabled",
        "announceChannel", "blacklistChannels",
    }
    data = {key: value for key, value in changes.items() if key in allowed}
    await ensure_guild(db, guild_id)
    return await db.levelconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


async def list_level_roles(db: Prisma, guild_id: str) -> list[Any]:
    """Return configured level rewards in ascending level order."""
    return await db.levelrole.find_many(where={"guildId": guild_id}, order={"level": "asc"})


async def upsert_level_role(db: Prisma, guild_id: str, level: int, role_id: str) -> Any:
    """Assign or replace the role reward for one level."""
    if level < 1:
        raise ValueError("Reward level must be at least 1")
    config = await get_level_config(db, guild_id)
    if config is None:
        config = await upsert_level_config(db, guild_id)
    return await db.levelrole.upsert(
        where={"guildId_level": {"guildId": guild_id, "level": level}},
        data={
            "create": {"guildId": guild_id, "levelConfigId": config.id, "level": level, "roleId": role_id},
            "update": {"roleId": role_id, "levelConfigId": config.id},
        },
    )


async def remove_level_role(db: Prisma, guild_id: str, level: int) -> int:
    """Remove the reward configured for one level."""
    result = await db.levelrole.delete_many(where={"guildId": guild_id, "level": level})
    return result if isinstance(result, int) else result.count
