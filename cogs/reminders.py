"""Persistent user reminders for BypassX."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db.queries.reminders import (
    complete_reminder,
    create_reminder,
    delete_pending_reminders,
    delete_reminder,
    get_reminder,
    list_due_reminders,
    list_pending_reminders,
)
from ui.containers import error, information, success
from utils.time import DurationParseError, format_timestamp, humanize_duration, parse_duration

logger = logging.getLogger(__name__)


class RemindersCog(commands.Cog):
    """Create and deliver restart-safe personal reminders."""

    reminder = app_commands.Group(name="reminder", description="Create and manage personal reminders.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self._delivery_loop.start()

    def cog_unload(self) -> None:
        self._delivery_loop.cancel()

    async def _require_guild_or_channel(self, interaction: discord.Interaction) -> tuple[str | None, str] | None:
        if interaction.channel_id is None:
            await interaction.response.send_message(**error("This reminder needs a channel context."), ephemeral=True)
            return None
        return (str(interaction.guild_id) if interaction.guild_id else None, str(interaction.channel_id))

    @reminder.command(name="set", description="Set a reminder after a duration.")
    @app_commands.describe(duration="Duration such as 30m, 2h, or 1d 4h.", message="What should the reminder say?")
    async def set_reminder(self, interaction: discord.Interaction, duration: str, message: str) -> None:
        context = await self._require_guild_or_channel(interaction)
        if context is None:
            return
        if not message.strip():
            await interaction.response.send_message(**error("Reminder text cannot be empty."), ephemeral=True)
            return
        try:
            seconds = parse_duration(duration, maximum=365 * 86400)
        except DurationParseError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        guild_id, channel_id = context
        remind_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        reminder = await create_reminder(
            self.db,
            user_id=str(interaction.user.id),
            guild_id=guild_id,
            channel_id=channel_id,
            message=message[:1000],
            remind_at=remind_at,
        )
        await interaction.response.send_message(
            **success(f"Reminder `{reminder.id}` set for {format_timestamp(remind_at.timestamp())} ({humanize_duration(seconds)})."),
            ephemeral=True,
        )

    @reminder.command(name="list", description="List your pending reminders.")
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        rows = await list_pending_reminders(self.db, str(interaction.user.id))
        if not rows:
            await interaction.response.send_message(**information("Reminders", "You have no pending reminders."), ephemeral=True)
            return
        body = "\n".join(
            f"`{row.id}` · {format_timestamp(row.remindAt.timestamp())} · {row.message[:120]}"
            for row in rows
        )
        await interaction.response.send_message(**information("Pending Reminders", body), ephemeral=True)

    @reminder.command(name="cancel", description="Cancel one of your pending reminders.")
    @app_commands.describe(reminder_id="The reminder ID shown by /reminder list.")
    async def cancel(self, interaction: discord.Interaction, reminder_id: str) -> None:
        deleted = await delete_reminder(self.db, str(interaction.user.id), reminder_id)
        if deleted is None:
            await interaction.response.send_message(**error("Pending reminder not found."), ephemeral=True)
            return
        await interaction.response.send_message(**success("Reminder cancelled."), ephemeral=True)

    @reminder.command(name="clear", description="Cancel all of your pending reminders.")
    async def clear(self, interaction: discord.Interaction) -> None:
        count = await delete_pending_reminders(self.db, str(interaction.user.id))
        await interaction.response.send_message(**success(f"Cancelled `{count}` pending reminder(s)."), ephemeral=True)

    async def _deliver(self, reminder) -> None:
        view = information(
            "Reminder",
            f"<@{reminder.userId}>  {reminder.message}\n\nOriginally scheduled for {format_timestamp(reminder.remindAt.timestamp())}.",
        )["view"]
        delivered = False
        try:
            channel = self.bot.get_channel(int(reminder.channelId))
            if channel is not None and hasattr(channel, "send"):
                await channel.send(view=view)
                delivered = True
        except (discord.HTTPException, discord.Forbidden, ValueError):
            logger.info("Reminder channel unavailable for %s; attempting DM", reminder.id)
        if not delivered:
            try:
                user = self.bot.get_user(int(reminder.userId)) or await self.bot.fetch_user(int(reminder.userId))
                await user.send(view=view)
                delivered = True
            except (discord.HTTPException, discord.Forbidden, ValueError):
                logger.warning("Could not deliver reminder %s", reminder.id)
        await complete_reminder(self.db, reminder.id)

    @tasks.loop(seconds=30)
    async def _delivery_loop(self) -> None:
        try:
            for reminder in await list_due_reminders(self.db):
                await self._deliver(reminder)
        except Exception:
            logger.exception("Reminder delivery loop failed")

    @_delivery_loop.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._delivery_loop.is_running():
            self._delivery_loop.start()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RemindersCog(bot))
