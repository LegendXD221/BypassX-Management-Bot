"""Prefix-command and shared argument converters."""

from __future__ import annotations

from discord.ext import commands

from utils.time import DurationParseError, parse_duration


class MemberConverter(commands.MemberConverter):
    """Resolve a guild member from mention, ID, or searchable name."""


class RoleConverter(commands.RoleConverter):
    """Resolve a guild role from mention, ID, or name."""


class TextChannelConverter(commands.TextChannelConverter):
    """Resolve a text channel from mention, ID, or name."""


class SnowflakeConverter(commands.Converter[int]):
    """Convert a Discord snowflake string into an integer ID."""

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        try:
            value = int(argument.strip().strip("<@!#&>"))
        except ValueError as exc:
            raise commands.BadArgument("Expected a Discord ID.") from exc
        if value <= 0:
            raise commands.BadArgument("Discord ID must be positive.")
        return value


class DurationConverter(commands.Converter[int]):
    """Convert compact durations such as `15m` or `2h 30m` to seconds."""

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        try:
            return parse_duration(argument)
        except DurationParseError as exc:
            raise commands.BadArgument(str(exc)) from exc


__all__ = [
    "DurationConverter",
    "MemberConverter",
    "RoleConverter",
    "SnowflakeConverter",
    "TextChannelConverter",
]
