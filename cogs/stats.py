"""Live server statistics and statistics channels.

Category    : Server Stats
Emoji       : bx_pulse
Color       : #3498DB
Description : Server/member/bot overviews and live counter channels.
"""

from __future__ import annotations

import platform
import resource
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from db.queries.stats import (
    STAT_TYPES,
    delete_stat_channels,
    list_stat_channels,
    upsert_stat_channel,
)
from ui.containers import error, information, success

STATS_ACCENT = 0xE62334
STAT_LABELS = {
    "total_members": "Members",
    "online_members": "Online",
    "boosts": "Boosts",
    "channels": "Channels",
    "roles": "Roles",
    "bans": "Bans",
}
STAT_CHOICES = [app_commands.Choice(name=label, value=value) for value, label in STAT_LABELS.items()]


class StatsCog(commands.Cog):
    """Provide server statistics and maintain live counter channels."""

    stats = app_commands.Group(name="stats", description="View server and bot statistics.")
    statschannels = app_commands.Group(name="statschannels", description="Manage live statistics channels.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.started_at = datetime.now(timezone.utc)
        self._refreshing: set[int] = set()

    @staticmethod
    def _guild(interaction: discord.Interaction) -> discord.Guild | None:
        return interaction.guild

    async def _ban_count(self, guild: discord.Guild) -> int | None:
        """Fetch the ban count when the bot has permission; return None otherwise."""
        try:
            count = 0
            async for _ in guild.bans(limit=None):
                count += 1
            return count
        except (discord.Forbidden, discord.HTTPException):
            return None

    def _online_count(self, guild: discord.Guild) -> int:
        return sum(1 for member in guild.members if member.status != discord.Status.offline)

    @stats.command(name="server", description="View a full server overview.")
    async def server(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        bans = await self._ban_count(guild)
        body = (
            f"**Owner**  <@{guild.owner_id}>\n"
            f"**Created**  <t:{int(guild.created_at.timestamp())}:D>\n"
            f"**Members**  `{guild.member_count or len(guild.members):,}`\n"
            f"**Online**  `{self._online_count(guild):,}`\n"
            f"**Bots**  `{sum(member.bot for member in guild.members):,}`\n"
            f"**Channels**  `{len(guild.channels):,}`\n"
            f"**Roles**  `{max(0, len(guild.roles) - 1):,}`\n"
            f"**Boosts**  `{guild.premium_subscription_count or 0:,}` (level {guild.premium_tier})\n"
            f"**Bans**  `{bans if bans is not None else 'unavailable'}`"
        )
        await interaction.response.send_message(**information(f"Server Overview · {guild.name}", body, accent=STATS_ACCENT), ephemeral=True)

    @stats.command(name="member", description="View a detailed member profile.")
    @app_commands.describe(member="Member to inspect; defaults to yourself.")
    async def member(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        guild = self._guild(interaction)
        target = member or interaction.user
        if guild is None or not isinstance(target, discord.Member):
            await interaction.response.send_message(**error("This command requires a server member."), ephemeral=True)
            return
        joined = f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "unknown"
        created = f"<t:{int(target.created_at.timestamp())}:R>"
        roles = ", ".join(role.mention for role in target.roles[1:]) or "None"
        activity = target.activity.name if target.activity else "None"
        body = (
            f"**User**  {target.mention} · `{target.id}`\n"
            f"**Account created**  {created}\n**Joined server**  {joined}\n"
            f"**Status**  `{target.status}`\n**Activity**  `{activity}`\n"
            f"**Roles**  {roles}"
        )
        await interaction.response.send_message(**information(f"Member Profile · {target.display_name}", body, accent=STATS_ACCENT), ephemeral=True)

    @stats.command(name="bot", description="View bot uptime, latency, shard, and memory statistics.")
    async def bot_stats(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        uptime = datetime.now(timezone.utc) - self.started_at
        memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        shard = guild.shard_id if self.bot.shard_count else 0
        body = (
            f"**Uptime**  `{str(uptime).split('.')[0]}`\n"
            f"**Latency**  `{round(self.bot.latency * 1000)} ms`\n"
            f"**Shard**  `{shard}` / `{self.bot.shard_count or 1}`\n"
            f"**Memory**  `{memory_mb:.1f} MB`\n"
            f"**Python**  `{platform.python_version()}`\n"
            f"**Discord.py**  `{discord.__version__}`"
        )
        await interaction.response.send_message(**information("Bot Statistics", body, accent=STATS_ACCENT), ephemeral=True)

    @statschannels.command(name="setup", description="Deploy live-updating statistics channels.")
    @require_tier(2)
    async def channels_setup(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        category = discord.utils.get(guild.categories, name="Server Stats")
        if category is None:
            try:
                category = await guild.create_category("Server Stats", reason="Deploy live server statistics")
            except (discord.Forbidden, discord.HTTPException):
                await interaction.followup.send(**error("The bot could not create the Server Stats category."), ephemeral=True)
                return
        created = 0
        for stat_type in STAT_TYPES:
            existing = await self._configured_channel(guild, stat_type)
            if existing is None:
                try:
                    channel = await guild.create_voice_channel(
                        self._channel_name(stat_type, guild),
                        category=category,
                        reason="Deploy live server statistics",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    continue
                await upsert_stat_channel(self.db, str(guild.id), stat_type, str(channel.id))
                created += 1
        await self.refresh_guild(guild)
        await interaction.followup.send(**success(f"Live statistics deployed. Created `{created}` channel(s) in {category.name}."), ephemeral=True)

    @statschannels.command(name="disable", description="Remove live statistics channels.")
    @require_tier(2)
    async def channels_disable(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        rows = await list_stat_channels(self.db, str(guild.id))
        removed = 0
        for row in rows:
            channel = guild.get_channel(int(row.channelId))
            if channel is not None:
                try:
                    await channel.delete(reason="Disable live server statistics")
                    removed += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await delete_stat_channels(self.db, str(guild.id))
        await interaction.response.send_message(**success(f"Disabled live statistics and removed `{removed}` channel(s)."), ephemeral=True)

    @statschannels.command(name="config", description="Configure what a statistics channel displays.")
    @app_commands.describe(stat_type="Statistic represented by the channel.", channel="Voice channel to use for this statistic.")
    @app_commands.choices(stat_type=STAT_CHOICES)
    @require_tier(2)
    async def channels_config(self, interaction: discord.Interaction, stat_type: app_commands.Choice[str], channel: discord.VoiceChannel) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_stat_channel(self.db, str(guild.id), stat_type.value, str(channel.id))
        await self._rename_channel(channel, stat_type.value, guild)
        await interaction.response.send_message(**success(f"{stat_type.name} statistics will use {channel.mention}."), ephemeral=True)

    async def _configured_channel(self, guild: discord.Guild, stat_type: str) -> discord.VoiceChannel | None:
        row = await self.db.statchannel.find_unique(where={"guildId_type": {"guildId": str(guild.id), "type": stat_type}})
        if row is None:
            return None
        channel = guild.get_channel(int(row.channelId))
        return channel if isinstance(channel, discord.VoiceChannel) else None

    def _channel_name(self, stat_type: str, guild: discord.Guild) -> str:
        values = {
            "total_members": f"Members: {guild.member_count or len(guild.members)}",
            "online_members": f"Online: {self._online_count(guild)}",
            "boosts": f"Boosts: {guild.premium_subscription_count or 0}",
            "channels": f"Channels: {len(guild.channels)}",
            "roles": f"Roles: {max(0, len(guild.roles) - 1)}",
            "bans": "Bans: updating",
        }
        return values.get(stat_type, stat_type.replace("_", " ").title())[:100]

    async def _rename_channel(self, channel: discord.VoiceChannel, stat_type: str, guild: discord.Guild) -> None:
        name = self._channel_name(stat_type, guild)
        if channel.name != name:
            try:
                await channel.edit(name=name, reason="Update live server statistics")
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def refresh_guild(self, guild: discord.Guild) -> None:
        """Refresh every configured stat channel, guarded against overlapping updates."""
        if guild.id in self._refreshing:
            return
        self._refreshing.add(guild.id)
        try:
            rows = await list_stat_channels(self.db, str(guild.id))
            ban_count = None
            for row in rows:
                channel = guild.get_channel(int(row.channelId))
                if not isinstance(channel, discord.VoiceChannel):
                    continue
                if row.type == "bans" and ban_count is None:
                    ban_count = await self._ban_count(guild)
                name = self._channel_name(row.type, guild)
                if row.type == "bans" and ban_count is not None:
                    name = f"Bans: {ban_count}"
                if channel.name != name:
                    try:
                        await channel.edit(name=name[:100], reason="Update live server statistics")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
        finally:
            self._refreshing.discard(guild.id)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self.refresh_guild(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.refresh_guild(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.refresh_guild(member.guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.status != after.status or before.guild.premium_subscription_count != after.guild.premium_subscription_count:
            await self.refresh_guild(after.guild)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self.refresh_guild(channel.guild)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.refresh_guild(channel.guild)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self.refresh_guild(role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.refresh_guild(role.guild)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        await self.refresh_guild(after)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
