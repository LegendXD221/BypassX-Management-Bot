"""Persistent cooldowns stored in the shared Prisma Cooldown model."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import discord
from discord.ext import commands

P = ParamSpec("P")
R = TypeVar("R")


class PersistentCooldown(commands.CheckFailure):
    """Raised when a database-backed cooldown is still active."""

    def __init__(self, remaining: timedelta) -> None:
        self.remaining = remaining
        super().__init__(f"cooldown active for {remaining.total_seconds():.0f} seconds")


async def check_and_set_cooldown(
    db: Any,
    source: discord.Interaction | commands.Context,
    command: str,
    seconds: int,
) -> None:
    """Reject an active cooldown and persist the next expiry timestamp."""
    if seconds <= 0:
        return

    guild = getattr(source, "guild", None)
    user = getattr(source, "user", None) or getattr(source, "author", None)
    if user is None:
        return
    guild_id = str(getattr(guild, "id", "dm"))
    user_id = str(user.id)
    now = datetime.now(timezone.utc)
    where = {"guildId_userId_command": {
        "guildId": guild_id,
        "userId": user_id,
        "command": command,
    }}
    existing = await db.cooldown.find_unique(where=where)
    if existing is not None:
        expires_at = existing.expiresAt
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now:
            raise PersistentCooldown(expires_at - now)

    await db.cooldown.upsert(
        where=where,
        data={
            "create": {
                "guildId": guild_id,
                "userId": user_id,
                "command": command,
                "expiresAt": now + timedelta(seconds=seconds),
            },
            "update": {"expiresAt": now + timedelta(seconds=seconds)},
        },
    )


def persistent_cooldown(
    seconds: int,
    command: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorate a slash or prefix callback with a persistent cooldown."""
    if seconds < 0:
        raise ValueError("Cooldown seconds cannot be negative")

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        command_name = command or func.__name__

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
                raise RuntimeError("persistent_cooldown could not find an Interaction or Context")
            cog = args[0] if args and isinstance(args[0], commands.Cog) else None
            db = getattr(getattr(cog, "bot", None), "db", None)
            if db is not None:
                await check_and_set_cooldown(db, source, command_name, seconds)
            return await func(*args, **kwargs)

        return wrapped

    return decorator


__all__ = ["PersistentCooldown", "check_and_set_cooldown", "persistent_cooldown"]
