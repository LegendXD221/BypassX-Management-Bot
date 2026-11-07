"""Moderation Cog.

Category    : Moderation
Emoji       : bx_shield
Color       : #ED4245
Description : Server moderation controls.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from core.cooldowns import persistent_cooldown
from db.queries.mod import (
    clear_warnings,
    create_case,
    create_warning,
    delete_warning,
    get_case,
    list_cases,
    list_warnings,
    update_case_reason,
)
from ui.containers import error, information, success, warning
from utils.time import DurationParseError, humanize_duration, parse_duration


class ModerationCog(commands.Cog):
    """Execute moderation actions and persist their case history."""

    role = app_commands.Group(name="role", description="Manage member roles.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    @staticmethod
    def _guild(interaction: discord.Interaction) -> discord.Guild | None:
        return interaction.guild

    async def _record(
        self,
        interaction: discord.Interaction,
        target_id: str,
        action: str,
        reason: str | None,
        duration: int | None = None,
    ):
        guild = self._guild(interaction)
        if guild is None or interaction.user is None:
            return None
        case = await create_case(
            self.db,
            str(guild.id),
            target_id,
            str(interaction.user.id),
            action,
            reason,
            duration,
        )
        logging_cog = self.bot.get_cog("LoggingCog")
        if logging_cog is not None:
            try:
                await logging_cog.emit_mod_action(
                    guild,
                    action=action,
                    target_id=target_id,
                    moderator_id=str(interaction.user.id),
                    reason=reason,
                    case_id=case.id,
                    duration=str(duration) if duration is not None else None,
                )
            except Exception:
                # A logging-channel failure must never undo the moderation
                # action or make the command appear unsuccessful.
                logging.getLogger(__name__).exception("Could not emit moderation audit case %s", case.id)
        return case

    async def _require_guild(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is not None:
            return True
        await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
        return False

    @app_commands.command(name="ban", description="Ban a member permanently.")
    @app_commands.describe(member="Member to ban.", reason="Reason for the ban.")
    @require_tier(1)
    @persistent_cooldown(3)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        await member.ban(reason=reason, delete_message_days=0)
        case = await self._record(interaction, str(member.id), "BAN", reason)
        await interaction.response.send_message(**success(f"Banned {member.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="kick", description="Remove a member from the server.")
    @app_commands.describe(member="Member to kick.", reason="Reason for the kick.")
    @require_tier(1)
    @persistent_cooldown(3)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        await member.kick(reason=reason)
        case = await self._record(interaction, str(member.id), "KICK", reason)
        await interaction.response.send_message(**success(f"Kicked {member.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="timeout", description="Mute a member for a set duration.")
    @app_commands.describe(member="Member to timeout.", duration="Duration such as 30m or 2h.", reason="Reason for the timeout.")
    @require_tier(1)
    @persistent_cooldown(3)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        try:
            seconds = parse_duration(duration, maximum=28 * 86400)
        except DurationParseError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        await member.timeout(timedelta(seconds=seconds), reason=reason)
        case = await self._record(interaction, str(member.id), "TIMEOUT", reason, seconds)
        await interaction.response.send_message(
            **success(f"Timed out {member.mention} for {humanize_duration(seconds)}. Case `#{case.id}`."),
            ephemeral=True,
        )

    @app_commands.command(name="untimeout", description="Remove a member timeout.")
    @app_commands.describe(member="Member to untimeout.", reason="Reason for removing the timeout.")
    @require_tier(1)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        await member.timeout(None, reason=reason)
        case = await self._record(interaction, str(member.id), "UNTIMEOUT", reason)
        await interaction.response.send_message(**success(f"Removed timeout from {member.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="warn", description="Issue a formal warning.")
    @app_commands.describe(member="Member to warn.", reason="Reason for the warning.")
    @require_tier(1)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not await self._require_guild(interaction):
            return
        case = await self._record(interaction, str(member.id), "WARN", reason)
        await create_warning(self.db, str(interaction.guild.id), str(member.id), str(interaction.user.id), reason, case.id)
        await interaction.response.send_message(**success(f"Warning issued to {member.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="warnings", description="View a member's warning history.")
    @app_commands.describe(member="Member whose warnings should be shown.")
    @require_tier(1)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._require_guild(interaction):
            return
        rows = await list_warnings(self.db, str(interaction.guild.id), str(member.id))
        body = "\n".join(f"• `#{row.id}` · {row.reason} · <@{row.moderatorId}>" for row in rows) or "No warnings recorded."
        await interaction.response.send_message(**information(f"Warnings · {member}", body, accent=0xE62334), ephemeral=True)

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member.")
    @app_commands.describe(member="Member whose warnings should be cleared.")
    @require_tier(2)
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._require_guild(interaction):
            return
        count = await clear_warnings(self.db, str(interaction.guild.id), str(member.id))
        await interaction.response.send_message(**success(f"Cleared `{count}` warnings for {member.mention}."), ephemeral=True)

    @app_commands.command(name="delwarn", description="Delete a specific warning by ID.")
    @app_commands.describe(warning_id="Warning record ID.")
    @require_tier(2)
    async def delwarn(self, interaction: discord.Interaction, warning_id: int) -> None:
        if not await self._require_guild(interaction):
            return
        count = await delete_warning(self.db, str(interaction.guild.id), warning_id)
        if count == 0:
            await interaction.response.send_message(**error("Warning record not found."), ephemeral=True)
            return
        await interaction.response.send_message(**success(f"Deleted warning `#{warning_id}`."), ephemeral=True)

    @app_commands.command(name="purge", description="Bulk delete messages, up to 1000.")
    @app_commands.describe(amount="Number of messages to delete.")
    @require_tier(1)
    @persistent_cooldown(5)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000]) -> None:
        if not await self._require_guild(interaction):
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(**error("This command requires a text channel."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await channel.purge(limit=int(amount))
        case = await self._record(interaction, str(channel.id), "PURGE", f"Deleted {len(deleted)} messages")
        await interaction.followup.send(**success(f"Deleted `{len(deleted)}` messages. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="lock", description="Lock the current channel.")
    @require_tier(1)
    async def lock(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild(interaction):
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(**error("This command requires a text channel."), ephemeral=True)
            return
        await channel.set_permissions(interaction.guild.default_role, send_messages=False, reason="Channel locked")
        case = await self._record(interaction, str(channel.id), "LOCK", None)
        await interaction.response.send_message(**success(f"Locked {channel.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock the current channel.")
    @require_tier(1)
    async def unlock(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild(interaction):
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(**error("This command requires a text channel."), ephemeral=True)
            return
        await channel.set_permissions(interaction.guild.default_role, send_messages=None, reason="Channel unlocked")
        case = await self._record(interaction, str(channel.id), "UNLOCK", None)
        await interaction.response.send_message(**success(f"Unlocked {channel.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="slowmode", description="Set or clear channel slowmode.")
    @app_commands.describe(seconds="Slowmode seconds, from 0 to 21600.")
    @require_tier(1)
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]) -> None:
        if not await self._require_guild(interaction):
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(**error("This command requires a text channel."), ephemeral=True)
            return
        await channel.edit(slowmode_delay=int(seconds), reason="Slowmode updated")
        case = await self._record(interaction, str(channel.id), "SLOWMODE", f"{seconds} seconds")
        await interaction.response.send_message(**success(f"Slowmode set to `{seconds}` seconds. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="softban", description="Ban and immediately unban to clear messages.")
    @app_commands.describe(member="Member to softban.", reason="Reason for the softban.")
    @require_tier(1)
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        await member.ban(reason=reason, delete_message_days=1)
        await interaction.guild.unban(discord.Object(id=member.id), reason="Softban release")
        case = await self._record(interaction, str(member.id), "SOFTBAN", reason)
        await interaction.response.send_message(**success(f"Softbanned {member.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="unban", description="Revoke a member ban.")
    @app_commands.describe(user_id="Banned user's Discord ID.", reason="Reason for the unban.")
    @require_tier(1)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        try:
            target_id = int(user_id.strip())
        except ValueError:
            await interaction.response.send_message(**error("User ID must be numeric."), ephemeral=True)
            return
        await interaction.guild.unban(discord.Object(id=target_id), reason=reason)
        case = await self._record(interaction, str(target_id), "UNBAN", reason)
        await interaction.response.send_message(**success(f"Unbanned `<@{target_id}>`. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="case", description="View a specific moderation case.")
    @app_commands.describe(case_id="Case ID to view.")
    @require_tier(1)
    async def case(self, interaction: discord.Interaction, case_id: int) -> None:
        if not await self._require_guild(interaction):
            return
        row = await get_case(self.db, case_id)
        if row is None or row.guildId != str(interaction.guild.id):
            await interaction.response.send_message(**error("Case not found."), ephemeral=True)
            return
        body = (
            f"**Target**  <@{row.targetId}>\n**Moderator**  <@{row.moderatorId}>\n"
            f"**Action**  `{row.action}`\n**Reason**  {row.reason or 'No reason provided.'}\n"
            f"**Duration**  {humanize_duration(row.duration) if row.duration else 'Permanent'}"
        )
        await interaction.response.send_message(**information(f"Case #{row.id}", body, accent=0xE62334), ephemeral=True)

    @app_commands.command(name="modlogs", description="View all moderation actions for a user.")
    @app_commands.describe(member="Member whose moderation history should be shown.")
    @require_tier(1)
    async def modlogs(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._require_guild(interaction):
            return
        rows = await list_cases(self.db, str(interaction.guild.id), str(member.id), limit=25)
        body = "\n".join(f"• `#{row.id}` · `{row.action}` · {row.reason or 'No reason provided.'}" for row in rows) or "No moderation cases recorded."
        await interaction.response.send_message(**information(f"Moderation Logs · {member}", body, accent=0xE62334), ephemeral=True)

    @app_commands.command(name="reason", description="Edit the reason on an existing case.")
    @app_commands.describe(case_id="Case ID.", reason="New case reason.")
    @require_tier(2)
    async def reason(self, interaction: discord.Interaction, case_id: int, reason: str) -> None:
        if not await self._require_guild(interaction):
            return
        row = await get_case(self.db, case_id)
        if row is None or row.guildId != str(interaction.guild.id):
            await interaction.response.send_message(**error("Case not found."), ephemeral=True)
            return
        await update_case_reason(self.db, case_id, reason)
        await interaction.response.send_message(**success(f"Updated reason for case `#{case_id}`."), ephemeral=True)

    @app_commands.command(name="massban", description="Ban multiple members by ID at once.")
    @app_commands.describe(user_ids="Space- or comma-separated Discord user IDs.", reason="Reason for the bans.")
    @require_tier(2)
    async def massban(self, interaction: discord.Interaction, user_ids: str, reason: str = "No reason provided.") -> None:
        if not await self._require_guild(interaction):
            return
        ids = [part for part in user_ids.replace(",", " ").split() if part.isdigit()][:100]
        if not ids:
            await interaction.response.send_message(**error("No valid user IDs were provided."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = 0
        for user_id in ids:
            try:
                await interaction.guild.ban(discord.Object(id=int(user_id)), reason=reason, delete_message_days=0)
            except discord.HTTPException:
                continue
            await self._record(interaction, user_id, "MASSBAN", reason)
            count += 1
        await interaction.followup.send(**success(f"Banned `{count}` members."), ephemeral=True)

    @app_commands.command(name="hide", description="Hide a channel from everyone.")
    @app_commands.describe(channel="Channel to hide.")
    @require_tier(2)
    async def hide(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await self._require_guild(interaction):
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=False, reason="Channel hidden")
        case = await self._record(interaction, str(channel.id), "HIDE", None)
        await interaction.response.send_message(**success(f"Hidden {channel.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="unhide", description="Restore a hidden channel's visibility.")
    @app_commands.describe(channel="Channel to unhide.")
    @require_tier(2)
    async def unhide(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await self._require_guild(interaction):
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=None, reason="Channel unhidden")
        case = await self._record(interaction, str(channel.id), "UNHIDE", None)
        await interaction.response.send_message(**success(f"Unhidden {channel.mention}. Case `#{case.id}`."), ephemeral=True)

    @app_commands.command(name="nuke", description="Clone and delete a channel, wiping its history.")
    @app_commands.describe(channel="Text channel to replace.")
    @require_tier(2)
    async def nuke(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await self._require_guild(interaction):
            return
        new_channel = await channel.clone(reason=f"Nuked by {interaction.user}")
        await channel.delete(reason=f"Nuked by {interaction.user}")
        await self._record(interaction, str(channel.id), "NUKE", None)
        await interaction.response.send_message(**success(f"Replaced `{channel.name}` with {new_channel.mention}."), ephemeral=True)

    @role.command(name="add", description="Add a role to a member.")
    @app_commands.describe(member="Member to update.", role="Role to add.")
    @require_tier(1)
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if not await self._require_guild(interaction):
            return
        await member.add_roles(role, reason=f"Role added by {interaction.user}")
        await self._record(interaction, str(member.id), "ROLE_ADD", role.name)
        await interaction.response.send_message(**success(f"Added {role.mention} to {member.mention}."), ephemeral=True)

    @role.command(name="remove", description="Remove a role from a member.")
    @app_commands.describe(member="Member to update.", role="Role to remove.")
    @require_tier(1)
    async def role_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if not await self._require_guild(interaction):
            return
        await member.remove_roles(role, reason=f"Role removed by {interaction.user}")
        await self._record(interaction, str(member.id), "ROLE_REMOVE", role.name)
        await interaction.response.send_message(**success(f"Removed {role.mention} from {member.mention}."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
