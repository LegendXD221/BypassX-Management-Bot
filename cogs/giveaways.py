"""Persistent giveaways for BypassX.

Category    : Giveaways
Emoji       : bx_gift
Color       : #E91E63
Description : Launch and manage secure server giveaways.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.checks import require_tier
from config.emojis import E
from db.queries.giveaways import (
    add_entry,
    create_giveaway,
    delete_giveaway,
    get_giveaway,
    list_active_giveaways,
    list_due_giveaways,
    list_finished_giveaways,
    update_giveaway,
)
from ui.containers import error, information, success
from utils.time import DurationParseError, format_timestamp, humanize_duration, parse_duration

logger = logging.getLogger(__name__)


class GiveawayPanelView(discord.ui.LayoutView):
    """Persistent Components V2 entry panel for a giveaway."""

    def __init__(self, cog: "GiveawaysCog", giveaway_id: str, *, prize: str, ends_at: datetime, winners: int, entries: int, paused: bool = False, ended: bool = False, winner_text: str | None = None) -> None:
        super().__init__(timeout=None)
        status = "ENDED" if ended else "PAUSED" if paused else "OPEN"
        details = (
            f"**Prize**  {prize}\n"
            f"**Winners**  `{winners}`\n"
            f"**Entries**  `{entries}`\n"
            f"**Status**  `{status}`\n"
            f"**Ends**  {format_timestamp(ends_at.timestamp())}"
        )
        if winner_text:
            details += f"\n\n**Winner(s)**\n{winner_text}"
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{E.bx_gift}  **BypassX Giveaway**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(details),
                accent_color=0xE91E63,
            )
        )
        button = discord.ui.Button(
            label="Enter Giveaway" if not ended and not paused else "Giveaway Ended" if ended else "Giveaway Paused",
            style=discord.ButtonStyle.success if not ended and not paused else discord.ButtonStyle.secondary,
            custom_id=f"giveaway:enter:{giveaway_id}",
            disabled=ended or paused,
        )
        button.callback = self._enter
        self.add_item(discord.ui.ActionRow(button))
        self._cog = cog
        self._giveaway_id = giveaway_id

    async def _enter(self, interaction: discord.Interaction) -> None:
        await self._cog.enter_giveaway(interaction, self._giveaway_id)


class GiveawaysCog(commands.Cog):
    """Manage persistent, restart-safe server giveaways."""

    giveaway = app_commands.Group(name="giveaway", description="Launch and manage giveaways.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self._expiry_loop.start()

    async def cog_load(self) -> None:
        """Restore active giveaway buttons after a reconnect or process restart."""
        rows = await self.db.giveaway.find_many(where={"ended": False})
        for row in rows:
            self.bot.add_view(self._view_for(row), message_id=int(row.messageId) if row.messageId.isdigit() else None)

    def cog_unload(self) -> None:
        self._expiry_loop.cancel()

    def _view_for(self, row) -> GiveawayPanelView:
        return GiveawayPanelView(
            self,
            row.id,
            prize=row.prize,
            ends_at=row.endsAt,
            winners=row.winnersCount,
            entries=len(row.entries or []),
            paused=row.paused,
            ended=row.ended,
            winner_text=self._winner_text(row.winners or []) if row.ended else None,
        )

    @staticmethod
    def _winner_text(winners: list[str]) -> str:
        return ", ".join(f"<@{winner}>" for winner in winners) or "No eligible entries."

    async def _guild(self, interaction: discord.Interaction) -> discord.Guild | None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return None
        return interaction.guild

    async def enter_giveaway(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This giveaway can only be entered inside the server."), ephemeral=True)
            return
        row = await get_giveaway(self.db, str(interaction.guild.id), giveaway_id)
        if row is None or row.ended:
            await interaction.response.send_message(**error("This giveaway has ended or no longer exists."), ephemeral=True)
            return
        if row.paused:
            await interaction.response.send_message(**error("This giveaway is temporarily paused."), ephemeral=True)
            return
        if row.endsAt <= datetime.now(timezone.utc):
            await self._finish(row)
            await interaction.response.send_message(**error("This giveaway has ended."), ephemeral=True)
            return
        _, added = await add_entry(self.db, row.id, str(interaction.user.id))
        if not added:
            await interaction.response.send_message(**information("Giveaway", "You are already entered."), ephemeral=True)
            return
        await interaction.response.send_message(**success("Your entry has been recorded."), ephemeral=True)
        await self._refresh_panel(row.id)

    async def _refresh_panel(self, giveaway_id: str) -> None:
        row = await self.db.giveaway.find_unique(where={"id": giveaway_id})
        if row is None:
            return
        channel = self.bot.get_channel(int(row.channelId))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(row.messageId))
            await message.edit(view=self._view_for(row))
        except (discord.NotFound, discord.HTTPException, ValueError):
            logger.warning("Could not refresh giveaway panel %s", giveaway_id)

    async def _finish(self, row) -> list[str]:
        if row.ended:
            return list(row.winners or [])
        entries = list(dict.fromkeys(row.entries or []))
        winners: list[str] = []
        pool = entries[:]
        for _ in range(min(row.winnersCount, len(pool))):
            winner = secrets.choice(pool)
            pool.remove(winner)
            winners.append(winner)
        updated = await update_giveaway(self.db, row.id, ended=True, paused=False, winners=winners)
        await self._refresh_panel(updated.id)
        return winners

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._expiry_loop.is_running():
            self._expiry_loop.start()

    @tasks.loop(seconds=30)
    async def _expiry_loop(self) -> None:
        try:
            for row in await list_due_giveaways(self.db):
                await self._finish(row)
        except Exception:
            logger.exception("Giveaway expiry loop failed")

    @_expiry_loop.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()

    @giveaway.command(name="start", description="Launch a giveaway.")
    @app_commands.describe(prize="What is being given away.", duration="Duration such as 30m, 2h, or 1d.", winners="Number of winners, from 1 to 20.", channel="Channel for the public giveaway panel.")
    @require_tier(2)
    async def start(self, interaction: discord.Interaction, prize: str, duration: str, winners: app_commands.Range[int, 1, 20], channel: discord.TextChannel | None = None) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        destination = channel or interaction.channel
        if not isinstance(destination, discord.TextChannel):
            await interaction.response.send_message(**error("Choose a text channel for the giveaway panel."), ephemeral=True)
            return
        try:
            seconds = parse_duration(duration, maximum=30 * 86400)
        except DurationParseError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        ends_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        placeholder_id = uuid4().hex
        row = await create_giveaway(self.db, str(guild.id), channel_id=str(destination.id), message_id=f"pending-{placeholder_id}", prize=prize[:300], winners_count=int(winners), ends_at=ends_at, giveaway_id=placeholder_id)
        try:
            message = await destination.send(view=self._view_for(row))
            row = await update_giveaway(self.db, row.id, messageId=str(message.id))
            await message.edit(view=self._view_for(row))
            self.bot.add_view(self._view_for(row), message_id=message.id)
        except discord.HTTPException:
            await delete_giveaway(self.db, row.id)
            await interaction.response.send_message(**error("The giveaway panel could not be posted."), ephemeral=True)
            return
        await interaction.response.send_message(**success(f"Giveaway started in {destination.mention}; it ends in `{humanize_duration(seconds)}`."), ephemeral=True)

    @giveaway.command(name="end", description="Force-end an active giveaway.")
    @app_commands.describe(giveaway_id="Giveaway ID from the panel or list command.")
    @require_tier(2)
    async def end(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        row = await get_giveaway(self.db, str(guild.id), giveaway_id)
        if row is None or row.ended:
            await interaction.response.send_message(**error("Active giveaway not found."), ephemeral=True)
            return
        winners = await self._finish(row)
        await interaction.response.send_message(**success(f"Giveaway ended. Winner(s): {self._winner_text(winners)}"), ephemeral=True)

    @giveaway.command(name="reroll", description="Choose replacement winner(s) for a finished giveaway.")
    @app_commands.describe(giveaway_id="Finished giveaway ID.", winners="Number of replacement winners, from 1 to 20.")
    @require_tier(2)
    async def reroll(self, interaction: discord.Interaction, giveaway_id: str, winners: app_commands.Range[int, 1, 20] = 1) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        row = await get_giveaway(self.db, str(guild.id), giveaway_id)
        if row is None or not row.ended:
            await interaction.response.send_message(**error("Finished giveaway not found."), ephemeral=True)
            return
        pool = [entry for entry in (row.entries or []) if entry not in (row.winners or [])]
        selected: list[str] = []
        for _ in range(min(int(winners), len(pool))):
            winner = secrets.choice(pool)
            pool.remove(winner)
            selected.append(winner)
        if not selected:
            await interaction.response.send_message(**error("There are no eligible replacement entries."), ephemeral=True)
            return
        await update_giveaway(self.db, row.id, winners=list(row.winners or []) + selected)
        await self._refresh_panel(row.id)
        await interaction.response.send_message(**success(f"Rerolled winner(s): {self._winner_text(selected)}"), ephemeral=True)

    @giveaway.command(name="list", description="Show active giveaways in this server.")
    @require_tier(1)
    async def list(self, interaction: discord.Interaction) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        rows = await list_active_giveaways(self.db, str(guild.id))
        body = "\n".join(f"`{row.id}` · **{row.prize}** · `{len(row.entries or [])}` entries · {format_timestamp(row.endsAt.timestamp())}" for row in rows) or "No active giveaways."
        await interaction.response.send_message(**information("Active Giveaways", body), ephemeral=True)

    @giveaway.command(name="delete", description="Cancel and delete a giveaway.")
    @app_commands.describe(giveaway_id="Giveaway ID.")
    @require_tier(2)
    async def delete(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        row = await get_giveaway(self.db, str(guild.id), giveaway_id)
        if row is None:
            await interaction.response.send_message(**error("Giveaway not found."), ephemeral=True)
            return
        channel = guild.get_channel(int(row.channelId))
        if isinstance(channel, discord.TextChannel) and row.messageId.isdigit():
            try:
                message = await channel.fetch_message(int(row.messageId))
                await message.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
        await delete_giveaway(self.db, row.id)
        await interaction.response.send_message(**success("Giveaway cancelled and deleted."), ephemeral=True)

    @giveaway.command(name="pause", description="Pause entries for an active giveaway.")
    @app_commands.describe(giveaway_id="Giveaway ID.")
    @require_tier(2)
    async def pause(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await self._set_paused(interaction, giveaway_id, True)

    @giveaway.command(name="resume", description="Resume a paused giveaway.")
    @app_commands.describe(giveaway_id="Giveaway ID.")
    @require_tier(2)
    async def resume(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await self._set_paused(interaction, giveaway_id, False)

    async def _set_paused(self, interaction: discord.Interaction, giveaway_id: str, paused: bool) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        row = await get_giveaway(self.db, str(guild.id), giveaway_id)
        if row is None or row.ended:
            await interaction.response.send_message(**error("Active giveaway not found."), ephemeral=True)
            return
        await update_giveaway(self.db, row.id, paused=paused)
        await self._refresh_panel(row.id)
        await interaction.response.send_message(**success(f"Giveaway {'paused' if paused else 'resumed'}."), ephemeral=True)

    @giveaway.command(name="edit", description="Edit an active giveaway prize or end time.")
    @app_commands.describe(giveaway_id="Giveaway ID.", prize="New prize text.", duration="New duration from now, such as 2h.")
    @require_tier(2)
    async def edit(self, interaction: discord.Interaction, giveaway_id: str, prize: str | None = None, duration: str | None = None) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        row = await get_giveaway(self.db, str(guild.id), giveaway_id)
        if row is None or row.ended:
            await interaction.response.send_message(**error("Active giveaway not found."), ephemeral=True)
            return
        changes = {}
        if prize:
            changes["prize"] = prize[:300]
        if duration:
            try:
                changes["endsAt"] = datetime.now(timezone.utc) + timedelta(seconds=parse_duration(duration, maximum=30 * 86400))
            except DurationParseError as exc:
                await interaction.response.send_message(**error(str(exc)), ephemeral=True)
                return
        if not changes:
            await interaction.response.send_message(**error("Provide a new prize or duration."), ephemeral=True)
            return
        await update_giveaway(self.db, row.id, **changes)
        await self._refresh_panel(row.id)
        await interaction.response.send_message(**success("Giveaway updated."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawaysCog(bot))
