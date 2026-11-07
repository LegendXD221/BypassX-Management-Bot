"""Global error handling for prefix and application commands."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import TierDenied
from core.cooldowns import PersistentCooldown
from ui.containers import cooldown, error, permission_denied
from utils.time import humanize_duration


logger = logging.getLogger(__name__)


def _unwrap(error_value: Exception) -> Exception:
    """Unwrap Discord.py command wrappers to the original exception."""
    while isinstance(
        error_value,
        (commands.CommandInvokeError, app_commands.CommandInvokeError),
    ):
        error_value = error_value.original
    return error_value


def _payload(error_value: Exception) -> dict[str, Any] | None:
    """Map known errors to a safe user-facing Components V2 response."""
    error_value = _unwrap(error_value)
    if isinstance(error_value, (TierDenied, commands.CheckFailure, app_commands.CheckFailure)):
        if isinstance(error_value, TierDenied):
            logger.info("Permission denied: required tier %s", error_value.required)
        return permission_denied()
    if isinstance(error_value, PersistentCooldown):
        return cooldown(humanize_duration(int(error_value.remaining.total_seconds())))
    if isinstance(error_value, (commands.MissingRequiredArgument, commands.BadArgument)):
        return error(str(error_value) or "Check the command arguments.")
    if isinstance(error_value, app_commands.TransformerError):
        return error("One or more arguments could not be resolved.")
    if isinstance(error_value, discord.Forbidden):
        return error("The bot lacks permission to complete that action.")
    if isinstance(error_value, discord.NotFound):
        return error("The requested Discord object no longer exists.")
    if isinstance(error_value, discord.HTTPException):
        return error("Discord rejected the request. Try again shortly.")
    return None


async def handle_prefix_error(ctx: commands.Context, error_value: Exception) -> None:
    """Handle a prefix command error without producing raw text."""
    if isinstance(error_value, commands.CommandNotFound):
        return

    payload = _payload(error_value)
    if payload is None:
        logger.exception("Unhandled prefix command error", exc_info=error_value)
        payload = error("An internal error occurred.")
    await ctx.send(**payload)


async def handle_app_command_error(
    interaction: discord.Interaction,
    error_value: app_commands.AppCommandError,
) -> None:
    """Handle an application-command error with an ephemeral response."""
    payload = _payload(error_value)
    if payload is None:
        logger.exception("Unhandled application command error", exc_info=error_value)
        payload = error("An internal error occurred.")

    if interaction.response.is_done():
        await interaction.followup.send(**payload, ephemeral=True)
    else:
        await interaction.response.send_message(**payload, ephemeral=True)


__all__ = ["handle_app_command_error", "handle_prefix_error"]
