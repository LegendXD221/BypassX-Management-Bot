"""Moderation case and warning queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma


async def create_case(
    db: Prisma,
    guild_id: str,
    target_id: str,
    moderator_id: str,
    action: str,
    reason: str | None = None,
    duration: int | None = None,
) -> Any:
    """Persist a moderation action and return its case record."""
    return await db.modcase.create(
        data={
            "guildId": guild_id,
            "targetId": target_id,
            "moderatorId": moderator_id,
            "action": action.upper(),
            "reason": reason,
            "duration": duration,
        }
    )


async def get_case(db: Prisma, case_id: int) -> Any | None:
    """Fetch one moderation case by numeric case ID."""
    return await db.modcase.find_unique(where={"id": case_id})


async def list_cases(
    db: Prisma,
    guild_id: str,
    target_id: str | None = None,
    limit: int = 50,
) -> list[Any]:
    """List recent moderation cases, optionally filtered by target."""
    where: dict[str, Any] = {"guildId": guild_id}
    if target_id:
        where["targetId"] = target_id
    return await db.modcase.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=max(1, min(limit, 1000)),
    )


async def update_case_reason(db: Prisma, case_id: int, reason: str) -> Any:
    """Replace the reason attached to an existing moderation case."""
    return await db.modcase.update(
        where={"id": case_id},
        data={"reason": reason},
    )


async def create_warning(
    db: Prisma,
    guild_id: str,
    user_id: str,
    moderator_id: str,
    reason: str,
    case_id: int | None = None,
) -> Any:
    """Create a warning record linked to an optional moderation case."""
    return await db.warning.create(
        data={
            "guildId": guild_id,
            "userId": user_id,
            "moderatorId": moderator_id,
            "reason": reason,
            "caseId": case_id,
        }
    )


async def list_warnings(
    db: Prisma,
    guild_id: str,
    user_id: str,
    limit: int = 100,
) -> list[Any]:
    """Return a member's warning history, newest first."""
    return await db.warning.find_many(
        where={"guildId": guild_id, "userId": user_id},
        order={"createdAt": "desc"},
        take=max(1, min(limit, 1000)),
    )


async def clear_warnings(db: Prisma, guild_id: str, user_id: str) -> int:
    """Delete all warnings for a member and return the deleted count."""
    result = await db.warning.delete_many(
        where={"guildId": guild_id, "userId": user_id}
    )
    return result if isinstance(result, int) else result.count


async def delete_warning(db: Prisma, guild_id: str, warning_id: int) -> int:
    """Delete one warning owned by a guild and return the deleted count."""
    result = await db.warning.delete_many(
        where={"id": warning_id, "guildId": guild_id}
    )
    return result if isinstance(result, int) else result.count
