"""Tickets Cog.

Category    : Tickets
Emoji       : bx_ticket
Color       : #5865F2
Description : Support ticket panels, channels, claims, and transcripts.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import has_tier, require_tier
from config.emojis import E
from db.queries.tickets import (
    claim_ticket,
    close_ticket as close_ticket_record,
    count_open_tickets,
    create_ticket,
    get_open_ticket_for_user,
    get_ticket_by_channel,
    get_ticket_config,
    list_open_tickets,
    set_ticket_control_message,
    unclaim_ticket,
    upsert_ticket_config,
)
from ui.containers import error, information, success

logger = logging.getLogger(__name__)


class TicketPanelView(discord.ui.LayoutView):
    """Persistent Components V2 view that opens a ticket."""

    def __init__(self, cog: "TicketsCog", guild_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Open a ticket",
            emoji=E.bx_ticket,
            custom_id=f"bypassx:ticket-open:{guild_id}",
        )
        button.callback = self._open
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{E.bx_ticket}  **Support Tickets**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Press the button below to open a private support ticket."),
                discord.ui.ActionRow(button),
                accent_color=0xE62334,
            )
        )

    async def _open(self, interaction: discord.Interaction) -> None:
        await self.cog.create_ticket_from_interaction(interaction, self.guild_id)


class TicketControlView(discord.ui.LayoutView):
    """Persistent controls installed in every open ticket channel."""

    def __init__(self, cog: "TicketsCog", ticket_id: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_id = ticket_id
        close = discord.ui.Button(style=discord.ButtonStyle.danger, label="Close", custom_id=f"bypassx:ticket-close:{ticket_id}")
        claim = discord.ui.Button(style=discord.ButtonStyle.success, label="Claim", custom_id=f"bypassx:ticket-claim:{ticket_id}")
        unclaim = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Unclaim", custom_id=f"bypassx:ticket-unclaim:{ticket_id}")
        close.callback = self._close
        claim.callback = self._claim
        unclaim.callback = self._unclaim
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{E.bx_ticket}  **Ticket Controls**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Support staff can claim or release this ticket. The owner or staff can close it."),
                discord.ui.ActionRow(close, claim, unclaim),
                accent_color=0xE62334,
            )
        )

    async def _close(self, interaction: discord.Interaction) -> None:
        await self.cog.close_current_ticket(interaction, self.ticket_id)

    async def _claim(self, interaction: discord.Interaction) -> None:
        await self.cog.claim_current_ticket(interaction, self.ticket_id)

    async def _unclaim(self, interaction: discord.Interaction) -> None:
        await self.cog.unclaim_current_ticket(interaction, self.ticket_id)


class TicketsCog(commands.Cog):
    """Manage support ticket configuration and ticket channels."""

    ticket = app_commands.Group(name="ticket", description="Manage support tickets.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    async def cog_load(self) -> None:
        """Restore persistent panel and open-ticket controls after restart."""
        try:
            configs = await self.db.ticketconfig.find_many()
            for config in configs:
                if config.panelMsg:
                    self.bot.add_view(TicketPanelView(self, int(config.guildId)), message_id=int(config.panelMsg))
            tickets = await self.db.ticket.find_many(where={"status": "open"})
            for ticket in tickets:
                # New tickets persist their exact control message. For legacy
                # rows, register by custom_id so old panels remain usable.
                message_id = int(ticket.controlMessageId) if ticket.controlMessageId else None
                self.bot.add_view(TicketControlView(self, ticket.id), message_id=message_id)
        except Exception:
            logger.exception("Could not restore ticket views")

    async def _guild_required(self, interaction: discord.Interaction) -> discord.Guild | None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return None
        return interaction.guild

    async def _current_ticket(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return None
        return await get_ticket_by_channel(self.db, str(interaction.channel.id))

    async def _is_staff(self, interaction: discord.Interaction, config=None) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        config = config or await get_ticket_config(self.db, str(interaction.guild.id))
        if config and config.supportRole:
            role = interaction.guild.get_role(int(config.supportRole))
            if role and role in interaction.user.roles:
                return True
        return await has_tier(self.db, interaction, 2)

    async def _can_manage(self, interaction: discord.Interaction, ticket, config=None) -> bool:
        return str(interaction.user.id) == str(ticket.ownerId) or await self._is_staff(interaction, config)

    @ticket.command(name="setup", description="Deploy the ticket panel with a button.")
    @require_tier(2)
    async def setup_panel(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(**error("Run this command in a text channel."), ephemeral=True)
            return
        config = await get_ticket_config(self.db, str(guild.id))
        message = None
        if config and config.panelMsg:
            try:
                message = await interaction.channel.fetch_message(int(config.panelMsg))
                await message.edit(view=TicketPanelView(self, guild.id))
            except (discord.NotFound, discord.HTTPException):
                message = None
        if message is None:
            message = await interaction.channel.send(view=TicketPanelView(self, guild.id))
        await upsert_ticket_config(self.db, str(guild.id), panelMsg=str(message.id))
        await interaction.response.send_message(**success(f"Ticket panel deployed in {interaction.channel.mention}."), ephemeral=True)

    @ticket.command(name="category", description="Set the category where ticket channels open.")
    @app_commands.describe(category="Ticket channel category.")
    @require_tier(2)
    async def category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_ticket_config(self.db, str(guild.id), categoryId=str(category.id))
        await interaction.response.send_message(**success(f"Ticket category set to `{category.name}`."), ephemeral=True)

    @ticket.command(name="logs", description="Set the transcript log channel.")
    @app_commands.describe(channel="Transcript destination channel.")
    @require_tier(2)
    async def logs(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_ticket_config(self.db, str(guild.id), logChannel=str(channel.id))
        await interaction.response.send_message(**success(f"Ticket transcripts will be sent to {channel.mention}."), ephemeral=True)

    @ticket.command(name="role", description="Set the support team role.")
    @app_commands.describe(role="Role allowed to manage tickets.")
    @require_tier(2)
    async def role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_ticket_config(self.db, str(guild.id), supportRole=str(role.id))
        await interaction.response.send_message(**success(f"Ticket support role set to {role.mention}."), ephemeral=True)

    @ticket.command(name="limit", description="Set the maximum open tickets per user.")
    @app_commands.describe(maximum="Maximum open tickets per user, from 1 to 10.")
    @require_tier(2)
    async def limit(self, interaction: discord.Interaction, maximum: app_commands.Range[int, 1, 10]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_ticket_config(self.db, str(guild.id), maxPerUser=int(maximum))
        await interaction.response.send_message(**success(f"Ticket limit set to `{maximum}` open ticket(s) per user."), ephemeral=True)

    async def create_ticket_from_interaction(self, interaction: discord.Interaction, guild_id: int) -> None:
        if interaction.guild is None or interaction.guild.id != guild_id or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(**error("This ticket panel belongs to another server."), ephemeral=True)
            return
        config = await get_ticket_config(self.db, str(guild_id))
        if config is None or not config.categoryId:
            await interaction.response.send_message(**error("Tickets are not fully configured. Ask staff to set a category."), ephemeral=True)
            return
        open_count = await count_open_tickets(self.db, str(guild_id), str(interaction.user.id))
        if open_count >= config.maxPerUser:
            await interaction.response.send_message(**error(f"You already have the maximum of `{config.maxPerUser}` open ticket(s)."), ephemeral=True)
            return
        category = interaction.guild.get_channel(int(config.categoryId))
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(**error("The configured ticket category is unavailable."), ephemeral=True)
            return
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if config.supportRole:
            role = interaction.guild.get_role(int(config.supportRole))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        name = f"ticket-{re.sub(r'[^a-z0-9-]', '-', interaction.user.display_name.lower())[:20]}"
        channel = None
        ticket = None
        try:
            channel = await interaction.guild.create_text_channel(name=name, category=category, overwrites=overwrites, reason="Support ticket opened")
            ticket = await create_ticket(self.db, str(guild_id), str(channel.id), str(interaction.user.id))
            control_message = await channel.send(view=TicketControlView(self, ticket.id))
            await set_ticket_control_message(self.db, ticket.id, str(control_message.id))
        except (discord.Forbidden, discord.HTTPException):
            if ticket is not None:
                try:
                    await close_ticket_record(self.db, ticket.id)
                except Exception:
                    logger.exception("Could not close incomplete ticket record %s", ticket.id)
            if channel is not None:
                try:
                    await channel.delete(reason="Cleaning up an incomplete support ticket")
                except discord.HTTPException:
                    pass
            await interaction.response.send_message(**error("The bot could not create the ticket channel."), ephemeral=True)
            return
        except Exception:
            logger.exception("Ticket creation failed for guild %s and user %s", guild_id, interaction.user.id)
            if ticket is not None:
                try:
                    await close_ticket_record(self.db, ticket.id)
                except Exception:
                    logger.exception("Could not close incomplete ticket record %s", ticket.id)
            if channel is not None:
                try:
                    await channel.delete(reason="Cleaning up an incomplete support ticket")
                except discord.HTTPException:
                    pass
            await interaction.response.send_message(**error("The ticket could not be saved. Please try again."), ephemeral=True)
            return
        await interaction.response.send_message(**success(f"Your ticket has been opened: {channel.mention}"), ephemeral=True)

    async def _transcript(self, channel: discord.TextChannel) -> discord.File:
        lines = [f"Transcript: #{channel.name}", f"Generated: {datetime.now(timezone.utc).isoformat()}", ""]
        async for message in channel.history(limit=1000, oldest_first=True):
            timestamp = message.created_at.isoformat()
            content = message.content or "[component/attachment message]"
            attachments = " ".join(attachment.url for attachment in message.attachments)
            lines.append(f"[{timestamp}] {message.author} ({message.author.id}): {content} {attachments}".strip())
        return discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=f"{channel.name}-transcript.txt")

    async def close_current_ticket(self, interaction: discord.Interaction, ticket_id: str | None = None) -> None:
        ticket = await get_ticket_by_channel(self.db, str(interaction.channel.id)) if interaction.channel else None
        if ticket_id and (ticket is None or ticket.id != ticket_id):
            ticket = None
        if ticket is None or interaction.guild is None:
            await interaction.response.send_message(**error("This channel is not an open ticket."), ephemeral=True)
            return
        config = await get_ticket_config(self.db, str(interaction.guild.id))
        if not await self._can_manage(interaction, ticket, config):
            await interaction.response.send_message(**error("Only the ticket owner or support staff can close this ticket."), ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.response.defer(ephemeral=True)
        transcript = await self._transcript(interaction.channel)
        await close_ticket_record(self.db, ticket.id)
        if config and config.logChannel:
            log_channel = interaction.guild.get_channel(int(config.logChannel))
            if log_channel and hasattr(log_channel, "send"):
                await log_channel.send(**information("Ticket Transcript", f"**Ticket**  `{interaction.channel.name}`\n**Owner**  <@{ticket.ownerId}>\n**Closed by**  {interaction.user.mention}", accent=0xE62334), file=transcript)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass
        await interaction.followup.send(**success("Ticket closed and transcript archived."), ephemeral=True)

    async def claim_current_ticket(self, interaction: discord.Interaction, ticket_id: str) -> None:
        ticket = await self._current_ticket(interaction)
        config = await get_ticket_config(self.db, str(interaction.guild.id)) if interaction.guild else None
        if ticket is None or ticket.id != ticket_id or not await self._is_staff(interaction, config):
            await interaction.response.send_message(**error("Only configured support staff can claim tickets."), ephemeral=True)
            return
        await claim_ticket(self.db, ticket.id, str(interaction.user.id))
        await interaction.response.send_message(**success(f"Ticket claimed by {interaction.user.mention}."), ephemeral=True)

    async def unclaim_current_ticket(self, interaction: discord.Interaction, ticket_id: str) -> None:
        ticket = await self._current_ticket(interaction)
        config = await get_ticket_config(self.db, str(interaction.guild.id)) if interaction.guild else None
        if ticket is None or ticket.id != ticket_id or not await self._is_staff(interaction, config):
            await interaction.response.send_message(**error("Only configured support staff can unclaim tickets."), ephemeral=True)
            return
        await unclaim_ticket(self.db, ticket.id)
        await interaction.response.send_message(**success("Ticket claim released."), ephemeral=True)

    @ticket.command(name="close", description="Close the current ticket and archive its transcript.")
    async def close(self, interaction: discord.Interaction) -> None:
        await self.close_current_ticket(interaction)

    @ticket.command(name="add", description="Add a user to the current ticket.")
    @app_commands.describe(user="User to add to the ticket.")
    async def add(self, interaction: discord.Interaction, user: discord.Member) -> None:
        ticket = await self._current_ticket(interaction)
        config = await get_ticket_config(self.db, str(interaction.guild.id)) if interaction.guild else None
        if ticket is None or not await self._can_manage(interaction, ticket, config) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(**error("Only the ticket owner or support staff can manage this ticket."), ephemeral=True)
            return
        await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(**success(f"Added {user.mention} to the ticket."), ephemeral=True)

    @ticket.command(name="remove", description="Remove a user from the current ticket.")
    @app_commands.describe(user="User to remove from the ticket.")
    async def remove(self, interaction: discord.Interaction, user: discord.Member) -> None:
        ticket = await self._current_ticket(interaction)
        config = await get_ticket_config(self.db, str(interaction.guild.id)) if interaction.guild else None
        if ticket is None or not await self._can_manage(interaction, ticket, config) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(**error("Only the ticket owner or support staff can manage this ticket."), ephemeral=True)
            return
        await interaction.channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(**success(f"Removed {user.mention} from the ticket."), ephemeral=True)

    @ticket.command(name="rename", description="Rename the current ticket channel.")
    @app_commands.describe(name="New channel name.")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        ticket = await self._current_ticket(interaction)
        config = await get_ticket_config(self.db, str(interaction.guild.id)) if interaction.guild else None
        if ticket is None or not await self._can_manage(interaction, ticket, config) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(**error("Only the ticket owner or support staff can manage this ticket."), ephemeral=True)
            return
        name = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")[:90]
        if not name:
            await interaction.response.send_message(**error("Provide a valid channel name."), ephemeral=True)
            return
        await interaction.channel.edit(name=name, reason=f"Ticket renamed by {interaction.user}")
        await interaction.response.send_message(**success(f"Ticket renamed to `{name}`."), ephemeral=True)

    @ticket.command(name="claim", description="Claim the current ticket as the handling agent.")
    async def claim(self, interaction: discord.Interaction) -> None:
        ticket = await self._current_ticket(interaction)
        await self.claim_current_ticket(interaction, ticket.id if ticket else "")

    @ticket.command(name="unclaim", description="Release the current ticket claim.")
    async def unclaim(self, interaction: discord.Interaction) -> None:
        ticket = await self._current_ticket(interaction)
        await self.unclaim_current_ticket(interaction, ticket.id if ticket else "")

    @ticket.command(name="pin", description="Pin the ticket panel message in the current channel.")
    async def pin(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(**error("This command requires a text channel."), ephemeral=True)
            return
        ticket = await self._current_ticket(interaction)
        config = await get_ticket_config(self.db, str(interaction.guild.id)) if interaction.guild else None
        if ticket is None or not await self._can_manage(interaction, ticket, config):
            await interaction.response.send_message(**error("Only the ticket owner or support staff can pin the panel."), ephemeral=True)
            return
        bot_user = self.bot.user
        async for message in interaction.channel.history(limit=50, oldest_first=True):
            if bot_user is not None and message.author.id == bot_user.id:
                try:
                    await message.pin(reason=f"Ticket panel pinned by {interaction.user}")
                    await interaction.response.send_message(**success("Ticket panel pinned."), ephemeral=True)
                except discord.HTTPException:
                    await interaction.response.send_message(**error("The bot could not pin the panel."), ephemeral=True)
                return
        await interaction.response.send_message(**error("No bot ticket panel message was found."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketsCog(bot))
