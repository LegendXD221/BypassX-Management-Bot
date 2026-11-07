"""Logging Cog.

Category    : Logging
Emoji       : bx_log
Color       : #FEE75C
Description : Audit and event logging controls.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from db.queries.logging_config import (
    LOG_FIELDS,
    disable_log_event,
    get_log_config,
    reset_log_config,
    set_log_channel,
)
from ui.containers import audit_log, error, information, success

logger = logging.getLogger(__name__)

_EVENT_CHOICES = [
    app_commands.Choice(name=name.replace("_", " ").title(), value=name)
    for name in LOG_FIELDS
]


class LoggingCog(commands.Cog):
    """Configure event channels and emit structured audit logs."""

    logs = app_commands.Group(name="logs", description="Configure automatic audit logging.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    async def _configured_channel(
        self,
        guild: discord.Guild,
        event: str,
    ) -> discord.abc.Messageable | None:
        field = LOG_FIELDS.get(event)
        if field is None:
            return None
        try:
            config = await get_log_config(self.db, str(guild.id))
        except Exception:
            logger.exception("Could not read logging configuration for guild %s", guild.id)
            return None
        channel_id = getattr(config, field, None) if config else None
        if not channel_id:
            return None
        channel = self.bot.get_channel(int(channel_id))
        if channel is not None and hasattr(channel, "send"):
            return channel
        try:
            fetched = await self.bot.fetch_channel(int(channel_id))
        except (discord.HTTPException, ValueError):
            return None
        return fetched if hasattr(fetched, "send") else None

    async def _emit(
        self,
        guild: discord.Guild,
        event: str,
        details: str,
        *,
        accent: int = 0xFFFFFF,
    ) -> None:
        """Post one event if its category has a configured channel."""
        channel = await self._configured_channel(guild, event)
        if channel is None:
            return
        try:
            await channel.send(**audit_log(event, details, accent=accent))
        except discord.HTTPException:
            logger.exception("Failed to post %s log for guild %s", event, guild.id)

    async def emit_mod_action(
        self,
        guild: discord.Guild,
        *,
        action: str,
        target_id: str,
        moderator_id: str,
        reason: str | None,
        case_id: int | None = None,
        duration: str | None = None,
    ) -> None:
        """Emit a structured moderation case from another Cog.

        Keeping this bridge on the Logging Cog avoids a second database write
        and lets moderation actions use the same configured ``mod_actions``
        destination as automatic audit events.
        """
        details = (
            f"**Target**  <@{target_id}> (`{target_id}`)\n"
            f"**Moderator**  <@{moderator_id}> (`{moderator_id}`)\n"
            f"**Reason**  {(reason or 'No reason provided.')[:800]}\n"
            f"**Duration**  {duration or 'Permanent'}\n"
            f"**Case**  `{f'#{case_id}' if case_id is not None else 'not recorded'}`"
        )
        await self._emit(guild, "mod_actions", f"**Action**  `{action.upper()}`\n{details}", accent=0xE62334)

    @logs.command(name="set", description="Assign a log channel for an event type.")
    @app_commands.describe(event="Event category.", channel="Destination log channel.")
    @app_commands.choices(event=_EVENT_CHOICES)
    @require_tier(2)
    async def set(self, interaction: discord.Interaction, event: app_commands.Choice[str], channel: discord.TextChannel) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await set_log_channel(self.db, str(interaction.guild.id), event.value, str(channel.id))
        await interaction.response.send_message(**success(f"`{event.name}` logs will be sent to {channel.mention}."), ephemeral=True)

    @logs.command(name="view", description="View current logging configuration.")
    @require_tier(2)
    async def view(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        config = await get_log_config(self.db, str(interaction.guild.id))
        rows = []
        for event, field in LOG_FIELDS.items():
            channel_id = getattr(config, field, None) if config else None
            destination = f"<#{channel_id}>" if channel_id else "disabled"
            rows.append(f"• `{event}` → {destination}")
        await interaction.response.send_message(
            **information("Logging Configuration", "\n".join(rows), accent=0xFFFFFF),
            ephemeral=True,
        )

    @logs.command(name="disable", description="Disable logging for an event type.")
    @app_commands.describe(event="Event category to disable.")
    @app_commands.choices(event=_EVENT_CHOICES)
    @require_tier(2)
    async def disable(self, interaction: discord.Interaction, event: app_commands.Choice[str]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await disable_log_event(self.db, str(interaction.guild.id), event.value)
        await interaction.response.send_message(**success(f"Disabled `{event.name}` logging."), ephemeral=True)

    @logs.command(name="reset", description="Clear all logging configuration.")
    @require_tier(3)
    async def reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        count = await reset_log_config(self.db, str(interaction.guild.id))
        await interaction.response.send_message(**success(f"Cleared `{count}` logging configuration record(s)."), ephemeral=True)

    @logs.command(name="test", description="Send a test log to verify channel setup.")
    @app_commands.describe(event="Event category to test.")
    @app_commands.choices(event=_EVENT_CHOICES)
    @require_tier(2)
    async def test(self, interaction: discord.Interaction, event: app_commands.Choice[str]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        channel = await self._configured_channel(interaction.guild, event.value)
        if channel is None:
            await interaction.response.send_message(**error(f"No channel is configured for `{event.name}`."), ephemeral=True)
            return
        await channel.send(**audit_log("TEST", f"**Event category**  `{event.value}`\n**Triggered by**  {interaction.user.mention}", accent=0xFFFFFF))
        await interaction.response.send_message(**success(f"Test log sent for `{event.name}`."), ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        content = message.content or "[No cached text]"
        details = f"**Author**  {message.author.mention}\n**Channel**  {message.channel.mention}\n**Content**  {content[:1500]}"
        await self._emit(message.guild, "message_delete", details, accent=0xE62334)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        details = (
            f"**Author**  {before.author.mention}\n**Channel**  {before.channel.mention}\n"
            f"**Before**  {before.content[:700] or '[empty]'}\n**After**  {after.content[:700] or '[empty]'}"
        )
        await self._emit(before.guild, "message_edit", details, accent=0xFFFFFF)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._emit(member.guild, "member_join", f"**Member**  {member.mention}\n**Account**  `{member.id}`", accent=0xFFFFFF)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._emit(member.guild, "member_leave", f"**Member**  {member.mention}\n**Account**  `{member.id}`", accent=0xE62334)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._emit(guild, "ban_kick", f"**Action**  Ban\n**Target**  {user.mention}\n**Account**  `{user.id}`", accent=0xE62334)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._emit(guild, "ban_kick", f"**Action**  Unban\n**Target**  {user.mention}\n**Account**  `{user.id}`", accent=0xFFFFFF)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles != after.roles:
            added = [role.mention for role in after.roles if role not in before.roles]
            removed = [role.mention for role in before.roles if role not in after.roles]
            details = f"**Member**  {after.mention}\n**Added**  {', '.join(added) or 'None'}\n**Removed**  {', '.join(removed) or 'None'}"
            await self._emit(after.guild, "role_change", details, accent=0xE62334)
        changes = []
        if before.display_name != after.display_name:
            changes.append(f"**Display name**  `{before.display_name}` → `{after.display_name}`")
        if before.name != after.name:
            changes.append(f"**Username**  `{before.name}` → `{after.name}`")
        if before.avatar != after.avatar:
            changes.append("**Avatar**  changed")
        if changes:
            await self._emit(after.guild, "member_update", f"**Member**  {after.mention}\n" + "\n".join(changes), accent=0xFFFFFF)
        before_timeout = before.communication_disabled_until
        after_timeout = after.communication_disabled_until
        if before_timeout != after_timeout:
            action = "timeout" if after_timeout is not None else "untimeout"
            until = after_timeout.isoformat() if after_timeout else "cleared"
            await self._emit(
                after.guild,
                "ban_kick",
                f"**Action**  `{action.upper()}`\n**Member**  {after.mention}\n**Until**  `{until}`",
                accent=0xE62334 if after_timeout else 0xFFFFFF,
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._emit(
            role.guild,
            "role_change",
            f"**Action**  Created\n**Role**  {role.mention}\n**Name**  `{role.name}`",
            accent=0xFFFFFF,
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._emit(
            role.guild,
            "role_change",
            f"**Action**  Deleted\n**Role**  `@{role.name}`\n**ID**  `{role.id}`",
            accent=0xE62334,
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if before.name == after.name and before.permissions == after.permissions and before.color == after.color:
            return
        await self._emit(
            after.guild,
            "role_change",
            f"**Role**  {after.mention}\n**Before**  `{before.name}`\n**After**  `{after.name}`",
            accent=0xFFFFFF,
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._emit(channel.guild, "channel_change", f"**Action**  Created\n**Channel**  {channel.mention}\n**Name**  `{channel.name}`", accent=0xFFFFFF)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._emit(channel.guild, "channel_change", f"**Action**  Deleted\n**Channel**  `#{channel.name}`\n**ID**  `{channel.id}`", accent=0xE62334)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        if before.name == after.name and before.overwrites == after.overwrites:
            return
        await self._emit(after.guild, "channel_change", f"**Channel**  {after.mention}\n**Before**  `{before.name}`\n**After**  `{after.name}`", accent=0xFFFFFF)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        action = "joined" if before.channel is None else "left" if after.channel is None else "moved"
        channel = after.channel or before.channel
        await self._emit(member.guild, "voice_activity", f"**Member**  {member.mention}\n**Action**  {action}\n**Channel**  {channel.mention if channel else 'unknown'}", accent=0xE62334)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await self._emit(invite.guild, "invite_activity", f"**Invite**  `{invite.code}`\n**Channel**  {invite.channel.mention if invite.channel else 'unknown'}\n**Inviter**  {invite.inviter.mention if invite.inviter else 'unknown'}", accent=0xFFFFFF)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await self._emit(invite.guild, "invite_activity", f"**Invite deleted**  `{invite.code}`", accent=0xE62334)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        old = before.premium_subscription_count
        new = after.premium_subscription_count
        if old != new:
            action = "boost" if new > old else "unboost"
            await self._emit(after, "member_update", f"**Server boost**  `{action}`\n**Count**  `{old}` → `{new}`", accent=0xE62334 if new > old else 0xFFFFFF)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LoggingCog(bot))
