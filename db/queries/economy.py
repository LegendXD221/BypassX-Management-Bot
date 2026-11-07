"""Economy wallet, bank, shop, and configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma


async def get_or_create_wallet(db: Prisma, guild_id: str, user_id: str) -> Any:
    """Return a member wallet, creating it with zero balances when needed."""
    return await db.membereco.upsert(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={
            "create": {"guildId": guild_id, "userId": user_id},
            "update": {},
        },
    )


async def adjust_wallet(db: Prisma, guild_id: str, user_id: str, amount: int) -> Any:
    """Atomically adjust wallet balance by a signed amount."""
    await get_or_create_wallet(db, guild_id, user_id)
    return await db.membereco.update(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={"wallet": {"increment": amount}},
    )


async def transfer_to_bank(db: Prisma, guild_id: str, user_id: str, amount: int) -> Any:
    """Move coins from wallet to bank in one database transaction."""
    if amount < 0:
        raise ValueError("Transfer amount cannot be negative")
    await get_or_create_wallet(db, guild_id, user_id)
    return await db.membereco.update(
        where={"guildId_userId": {"guildId": guild_id, "userId": user_id}},
        data={
            "wallet": {"decrement": amount},
            "bank": {"increment": amount},
        },
    )


async def leaderboard(db: Prisma, guild_id: str, limit: int = 10) -> list[Any]:
    """Return members ordered by wallet balance."""
    return await db.membereco.find_many(
        where={"guildId": guild_id},
        order={"wallet": "desc"},
        take=max(1, min(limit, 100)),
    )


async def get_economy_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch the economy configuration for a guild."""
    return await db.ecoconfig.find_unique(where={"guildId": guild_id})


async def upsert_economy_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Create or update supported economy settings."""
    allowed = {"currency", "dailyAmt", "weeklyAmt"}
    data = {key: value for key, value in changes.items() if key in allowed}
    return await db.ecoconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


async def list_shop_items(db: Prisma, guild_id: str) -> list[Any]:
    """List all shop items configured for a guild."""
    return await db.shopitem.find_many(
        where={"guildId": guild_id},
        order={"price": "asc"},
    )
