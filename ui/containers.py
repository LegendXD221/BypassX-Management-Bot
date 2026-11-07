"""Reusable Components V2 response builders.

Every public builder returns keyword arguments suitable for
``interaction.response.send_message(**success(...))`` or ``ctx.send(...)``.
Legacy embeds and raw response content are intentionally not used.
"""

from __future__ import annotations

from typing import Any

import discord

from config.colors import ERROR, NEUTRAL, SUCCESS, WARNING
from config.emojis import E


def _view(*children: discord.ui.Item[discord.ui.LayoutView], accent: int) -> discord.ui.LayoutView:
    """Wrap Components V2 children in a single accent-colored container."""
    view = discord.ui.LayoutView(timeout=180)
    view.add_item(discord.ui.Container(*children, accent_color=accent))
    return view


def _display(text: str) -> discord.ui.TextDisplay:
    return discord.ui.TextDisplay(text)


def _response(icon: str, label: str, message: str, accent: int) -> dict[str, Any]:
    return {
        "view": _view(
            _display(f"{icon}  **{label}.**  {message}"),
            accent=accent,
        )
    }


def success(message: str) -> dict[str, Any]:
    """Build a green one-line success response."""
    return _response(E.bx_tick, "Done", message, SUCCESS)


def error(message: str) -> dict[str, Any]:
    """Build a red one-line error response."""
    return _response(E.bx_cross, "Failed", message, ERROR)


def warning(message: str) -> dict[str, Any]:
    """Build a yellow one-line warning response."""
    return _response(E.bx_warn, "Notice", message, WARNING)


def permission_denied() -> dict[str, Any]:
    """Build the standard restricted-access response."""
    return _response(
        E.bx_lock,
        "Restricted",
        "You don't hold the required permission.",
        NEUTRAL,
    )


def cooldown(time_remaining: str) -> dict[str, Any]:
    """Build the standard cooldown response."""
    return _response(E.bx_pulse, "Cooldown", f"Try again in {time_remaining}.", NEUTRAL)


def information(title: str, message: str, *, accent: int = NEUTRAL) -> dict[str, Any]:
    """Build a neutral informational response."""
    return {
        "view": _view(
            _display(f"{E.bx_pulse}  **{title}**"),
            discord.ui.Separator(),
            _display(message),
            accent=accent,
        )
    }


def action_log(
    action: str,
    target_tag: str,
    target_id: str,
    moderator_tag: str,
    moderator_id: str,
    reason: str | None,
    case_id: int,
    *,
    duration: str | None = None,
    timestamp: str | None = None,
    accent: int = NEUTRAL,
) -> dict[str, Any]:
    """Build the structured moderation action log container."""
    details = "\n".join(
        (
            f"**Target**      {target_tag}  ·  `{target_id}`",
            f"**Moderator**   {moderator_tag}  ·  `{moderator_id}`",
            f"**Reason**      {reason or 'No reason provided.'}",
            f"**Duration**    {duration or 'Permanent'}",
            f"**Case**        `#{case_id}`",
        )
    )
    footer = timestamp or "Timestamp unavailable"
    return {
        "view": _view(
            _display(f"{E.bx_log}  **{action.upper()}**"),
            discord.ui.Separator(),
            _display(details),
            discord.ui.Separator(),
            _display(f"{E.bx_arrow}  {footer}"),
            accent=accent,
        )
    }


def audit_log(event: str, details: str, *, accent: int = NEUTRAL) -> dict[str, Any]:
    """Build a structured automatic audit-event container."""
    return {
        "view": _view(
            _display(f"{E.bx_log}  **{event.upper()}**"),
            discord.ui.Separator(),
            _display(details),
            accent=accent,
        )
    }


__all__ = [
    "action_log",
    "audit_log",
    "cooldown",
    "error",
    "information",
    "permission_denied",
    "success",
    "warning",
]
