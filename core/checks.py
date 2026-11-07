"""Database-backed permission tiers for BypassX commands."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import discord
from discord import app_commands
from discord.ext import commands

P = ParamSpec("P")
R = TypeVar("R")


class TierDenied(commands.CheckFailure):
    """Raised when a caller does not meet the configured permission tier."""

    def __init__(self, required: int, actual: int = 0) -> None:
        self.required = required
        self.actual = actual
        super().__init__(f"permission tier {required} required")


def _guild_and_user(source: discord.Interaction | commands.Context) -> tuple[Any, Any]:
    return getattr(source, "guild", None), getattr(source, "user", None) or getattr(source, "author", None)


async def get_user_tier(
    db: Any,
    source: discord.Interaction | commands.Context,
) -> int:
    """Return a caller's highest configured tier for the current guild."""
    guild, user = _guild_and_user(source)
    if guild is None or user is None:
        return 0
    if getattr(guild, "owner_id", None) == getattr(user, "id", None):
        return 3

    rows = await db.modtier.find_many(where={"guildId": str(guild.id)})
    role_ids = {str(role.id) for role in getattr(user, "roles", ())}
    matching = (row.tier for row in rows if str(row.roleId) in role_ids)
    return max(matching, default=0)


async def has_tier(
    db: Any,
    source: discord.Interaction | commands.Context,
    required: int,
) -> bool:
    """Check whether a caller meets a required tier."""
    if required not in range(4):
        raise ValueError("Permission tier must be between 0 and 3")
    return await get_user_tier(db, source) >= required


def require_tier(required: int) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorate a slash or prefix command with a database tier check.

    The decorated Cog callback must receive an Interaction or Context as its
    first argument after ``self``.
    """
    if required not in range(4):
        raise ValueError("Permission tier must be between 0 and 3")

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            source = next(
                (
                    value
                    for value in args
                    if isinstance(value, (discord.Interaction, commands.Context))
                ),
                None,
            )
            if source is None:
                raise RuntimeError("require_tier could not find an Interaction or Context")

            cog = args[0] if args and isinstance(args[0], commands.Cog) else None
            db = getattr(getattr(cog, "bot", None), "db", None)
            if db is None or not await has_tier(db, source, required):
                actual = await get_user_tier(db, source) if db is not None else 0
                raise TierDenied(required, actual)
            return await func(*args, **kwargs)

        return wrapped

    return decorator


__all__ = ["TierDenied", "get_user_tier", "has_tier", "require_tier"]
