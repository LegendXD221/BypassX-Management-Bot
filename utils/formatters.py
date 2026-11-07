"""Shared formatting helpers for concise BypassX responses."""

from __future__ import annotations

from collections.abc import Iterable


def truncate(value: str, limit: int = 1000, suffix: str = "…") -> str:
    """Trim text to a safe display length without splitting the suffix."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if len(value) <= limit:
        return value
    if len(suffix) >= limit:
        return suffix[:limit]
    return value[: limit - len(suffix)].rstrip() + suffix


def mention(user_id: int | str) -> str:
    """Format a Discord user mention."""
    return f"<@{int(user_id)}>"


def channel_mention(channel_id: int | str) -> str:
    """Format a Discord channel mention."""
    return f"<#{int(channel_id)}>"


def role_mention(role_id: int | str) -> str:
    """Format a Discord role mention."""
    return f"<@&{int(role_id)}>"


def field(label: str, value: object, *, inline: bool = False) -> str:
    """Format a compact labeled value for a Components V2 text block."""
    marker = " ·" if inline else ""
    return f"**{label}**{marker} {value}"


def bullet_list(items: Iterable[object], *, empty: str = "None") -> str:
    """Format items as newline-separated bullet rows."""
    values = [str(item) for item in items]
    return empty if not values else "\n".join(f"• {item}" for item in values)


def command_row(command: str, description: str) -> str:
    """Format one help-menu command row."""
    return f"`{command}`  ·  {truncate(description, 180)}"


__all__ = [
    "bullet_list",
    "channel_mention",
    "command_row",
    "field",
    "mention",
    "role_mention",
    "truncate",
]
