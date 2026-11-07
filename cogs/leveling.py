"""Leveling Cog.

Category    : Leveling
Emoji       : bx_crown
Color       : #F1C40F
Description : XP tracking, rank cards, rewards, and leveling configuration.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from config.emojis import E
from db.queries.level import (
    add_xp,
    get_level_config,
    get_or_create_level,
    leaderboard as get_leaderboard,
    list_level_roles,
    remove_level_role,
    reset_level,
    set_level,
    set_xp,
    upsert_level_config,
    upsert_level_role,
)
from ui.containers import error, information, success


XP_ACCENT = 0xE62334


def level_for_xp(xp: int) -> int:
    """Calculate a level using the quadratic ``level² × 100`` curve."""
    return max(0, int((max(0, xp) / 100) ** 0.5))


def xp_for_level(level: int) -> int:
    """Return the XP threshold for a level."""
    return max(0, level * level * 100)


class LeaderboardView(discord.ui.LayoutView):
    """Paged Components V2 leaderboard with previous/next controls."""

    def __init__(self, guild: discord.Guild, rows: list, page: int = 1) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.rows = rows
        self.page = max(1, page)
        self.page_size = 10
        self.total_pages = max(1, (len(rows) + self.page_size - 1) // self.page_size)
        self.page = min(self.page, self.total_pages)
        start = (self.page - 1) * self.page_size
        current = rows[start : start + self.page_size]
        lines = []
        for offset, row in enumerate(current, start=start + 1):
            member = guild.get_member(int(row.userId))
            name = member.display_name if member else f"User {row.userId}"
            lines.append(f"**{offset}.** {name} · level `{row.level}` · `{row.xp:,}` XP")
        body = "\n".join(lines) or "No XP has been recorded yet."
        previous = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Previous",
            custom_id=f"bypassx:levels-prev:{guild.id}:{self.page}",
            disabled=self.page <= 1,
        )
        next_page = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Next",
            custom_id=f"bypassx:levels-next:{guild.id}:{self.page}",
            disabled=self.page >= self.total_pages,
        )
        previous.callback = self._previous
        next_page.callback = self._next
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{E.bx_crown}  **XP Leaderboard** · Page {self.page}/{self.total_pages}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(body),
                discord.ui.ActionRow(previous, next_page),
                accent_color=XP_ACCENT,
            )
        )

    async def _previous(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=LeaderboardView(self.guild, self.rows, self.page - 1))

    async def _next(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=LeaderboardView(self.guild, self.rows, self.page + 1))


class LevelingCog(commands.Cog):
    """Track message XP and manage server leveling features."""

    levelroles = app_commands.Group(name="levelroles", description="Manage level role rewards.")
    levelconfig = app_commands.Group(name="levelconfig", description="Configure XP and announcements.")
    xpblacklist = app_commands.Group(name="xpblacklist", description="Manage XP channel exclusions.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self._last_xp: dict[tuple[int, int], datetime] = {}

    async def _guild_required(self, interaction: discord.Interaction) -> discord.Guild | None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return None
        return interaction.guild

    @app_commands.command(name="rank", description="View your or another member's rank card.")
    @app_commands.describe(member="Member whose rank should be shown.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message(**error("A guild member is required."), ephemeral=True)
            return
        row = await get_or_create_level(self.db, str(guild.id), str(target.id))
        level = level_for_xp(row.xp)
        if level != row.level:
            row = await set_level(self.db, str(guild.id), str(target.id), level)
        current_floor = xp_for_level(level)
        next_floor = xp_for_level(level + 1)
        progress = max(0, row.xp - current_floor)
        needed = max(1, next_floor - current_floor)
        body = (
            f"**Member**  {target.mention}\n**Level**  `{level}`\n**XP**  `{row.xp:,}`\n"
            f"**Progress**  `{progress:,}` / `{needed:,}` to level `{level + 1}`\n"
            f"**Rank**  Use `/leaderboard` to view the server standings."
        )
        await interaction.response.send_message(**information(f"Rank · {target.display_name}", body, accent=XP_ACCENT), ephemeral=True)

    @app_commands.command(name="leaderboard", description="View the server XP leaderboard.")
    @app_commands.describe(page="Leaderboard page number.")
    async def leaderboard(self, interaction: discord.Interaction, page: app_commands.Range[int, 1, 10] = 1) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        rows = await get_leaderboard(self.db, str(guild.id), limit=100)
        await interaction.response.send_message(view=LeaderboardView(guild, rows, int(page)), ephemeral=True)

    @app_commands.command(name="setlevel", description="Manually set a member's level.")
    @app_commands.describe(member="Member to update.", level="New level.")
    @require_tier(2)
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: app_commands.Range[int, 0, 1000]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await set_level(self.db, str(guild.id), str(member.id), int(level))
        await set_xp(self.db, str(guild.id), str(member.id), xp_for_level(int(level)))
        await interaction.response.send_message(**success(f"Set {member.mention} to level `{level}`."), ephemeral=True)

    @app_commands.command(name="setxp", description="Manually set a member's XP value.")
    @app_commands.describe(member="Member to update.", xp="New XP value.")
    @require_tier(2)
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, xp: app_commands.Range[int, 0, 100000000]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await set_xp(self.db, str(guild.id), str(member.id), int(xp))
        await set_level(self.db, str(guild.id), str(member.id), level_for_xp(int(xp)))
        await interaction.response.send_message(**success(f"Set {member.mention} to `{xp:,}` XP."), ephemeral=True)

    @app_commands.command(name="resetlevel", description="Reset a member's level and XP.")
    @app_commands.describe(member="Member to reset.")
    @require_tier(2)
    async def resetlevel(self, interaction: discord.Interaction, member: discord.Member) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await reset_level(self.db, str(guild.id), str(member.id))
        await interaction.response.send_message(**success(f"Reset {member.mention}'s level and XP."), ephemeral=True)

    @levelroles.command(name="add", description="Assign a role reward at a specific level.")
    @app_commands.describe(level="Level at which the role is awarded.", role="Role reward.")
    @require_tier(2)
    async def levelroles_add(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000], role: discord.Role) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_level_role(self.db, str(guild.id), int(level), str(role.id))
        await interaction.response.send_message(**success(f"{role.mention} will be awarded at level `{level}`."), ephemeral=True)

    @levelroles.command(name="remove", description="Remove a level role reward.")
    @app_commands.describe(level="Level reward to remove.")
    @require_tier(2)
    async def levelroles_remove(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        count = await remove_level_role(self.db, str(guild.id), int(level))
        if not count:
            await interaction.response.send_message(**error("No reward is configured at that level."), ephemeral=True)
            return
        await interaction.response.send_message(**success(f"Removed the level `{level}` role reward."), ephemeral=True)

    @levelroles.command(name="list", description="View configured level role rewards.")
    @require_tier(2)
    async def levelroles_list(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        rows = await list_level_roles(self.db, str(guild.id))
        body = "\n".join(f"• Level `{row.level}` → <@&{row.roleId}>" for row in rows) or "No level role rewards configured."
        await interaction.response.send_message(**information("Level Role Rewards", body, accent=XP_ACCENT), ephemeral=True)

    @levelconfig.command(name="xp", description="Configure the XP gain range.")
    @app_commands.describe(xp_min="Minimum XP per eligible message.", xp_max="Maximum XP per eligible message.")
    @require_tier(2)
    async def levelconfig_xp(self, interaction: discord.Interaction, xp_min: app_commands.Range[int, 1, 1000], xp_max: app_commands.Range[int, 1, 1000]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        if int(xp_min) > int(xp_max):
            await interaction.response.send_message(**error("Minimum XP cannot exceed maximum XP."), ephemeral=True)
            return
        await upsert_level_config(self.db, str(guild.id), enabled=True, xpMin=int(xp_min), xpMax=int(xp_max))
        await interaction.response.send_message(**success(f"XP gain range set to `{xp_min}`–`{xp_max}`."), ephemeral=True)

    @levelconfig.command(name="cooldown", description="Set the XP gain cooldown in seconds.")
    @app_commands.describe(seconds="Cooldown from 0 to 86400 seconds.")
    @require_tier(2)
    async def levelconfig_cooldown(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 86400]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_level_config(self.db, str(guild.id), cooldown=int(seconds))
        await interaction.response.send_message(**success(f"XP cooldown set to `{seconds}` seconds."), ephemeral=True)

    @levelconfig.command(name="message", description="Toggle level-up announcement messages.")
    @app_commands.describe(enabled="Whether level-up messages are enabled.")
    @require_tier(2)
    async def levelconfig_message(self, interaction: discord.Interaction, enabled: bool) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_level_config(self.db, str(guild.id), announceEnabled=enabled)
        await interaction.response.send_message(**success(f"Level-up announcements {'enabled' if enabled else 'disabled'}."), ephemeral=True)

    @levelconfig.command(name="channel", description="Set the level-up announcement channel.")
    @app_commands.describe(channel="Announcement channel.")
    @require_tier(2)
    async def levelconfig_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_level_config(self.db, str(guild.id), announceChannel=str(channel.id), announceEnabled=True)
        await interaction.response.send_message(**success(f"Level-up announcements will be sent to {channel.mention}."), ephemeral=True)

    @xpblacklist.command(name="add", description="Prevent XP gain in a channel.")
    @app_commands.describe(channel="Channel to blacklist.")
    @require_tier(2)
    async def xpblacklist_add(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await get_level_config(self.db, str(guild.id))
        channels = list(config.blacklistChannels) if config else []
        if str(channel.id) not in channels:
            channels.append(str(channel.id))
        await upsert_level_config(self.db, str(guild.id), blacklistChannels=channels[:100])
        await interaction.response.send_message(**success(f"Added {channel.mention} to the XP blacklist."), ephemeral=True)

    @xpblacklist.command(name="remove", description="Remove a channel from the XP blacklist.")
    @app_commands.describe(channel="Channel to remove.")
    @require_tier(2)
    async def xpblacklist_remove(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await get_level_config(self.db, str(guild.id))
        channels = [value for value in (list(config.blacklistChannels) if config else []) if value != str(channel.id)]
        await upsert_level_config(self.db, str(guild.id), blacklistChannels=channels)
        await interaction.response.send_message(**success(f"Removed {channel.mention} from the XP blacklist."), ephemeral=True)

    @xpblacklist.command(name="view", description="View blacklisted XP channels.")
    @require_tier(2)
    async def xpblacklist_view(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await get_level_config(self.db, str(guild.id))
        channels = list(config.blacklistChannels) if config else []
        body = "\n".join(f"• <#{channel_id}>" for channel_id in channels) or "No XP channels are blacklisted."
        await interaction.response.send_message(**information("XP Blacklist", body, accent=XP_ACCENT), ephemeral=True)

    async def _announce(self, message: discord.Message, config, member: discord.Member, level: int, roles: list[discord.Role]) -> None:
        if not config.announceEnabled:
            return
        channel = message.guild.get_channel(int(config.announceChannel)) if config.announceChannel else message.channel
        if channel is None or not hasattr(channel, "send"):
            return
        reward = "\n**Rewards**  " + ", ".join(role.mention for role in roles) if roles else ""
        await channel.send(**information("Level Up!", f"{member.mention} reached level `{level}`!{reward}", accent=XP_ACCENT))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return
        config = await get_level_config(self.db, str(message.guild.id))
        if config is None:
            config = await upsert_level_config(self.db, str(message.guild.id))
        if not config.enabled or str(message.channel.id) in config.blacklistChannels:
            return
        now = datetime.now(timezone.utc)
        key = (message.guild.id, message.author.id)
        last = self._last_xp.get(key)
        if last is not None and now - last < timedelta(seconds=config.cooldown):
            return
        self._last_xp[key] = now
        amount = random.randint(config.xpMin, config.xpMax)
        before = await get_or_create_level(self.db, str(message.guild.id), str(message.author.id))
        updated = await add_xp(self.db, str(message.guild.id), str(message.author.id), amount)
        old_level = max(before.level, level_for_xp(before.xp))
        new_level = level_for_xp(updated.xp)
        if new_level <= old_level:
            return
        await set_level(self.db, str(message.guild.id), str(message.author.id), new_level)
        reward_rows = await list_level_roles(self.db, str(message.guild.id))
        rewards: list[discord.Role] = []
        for row in reward_rows:
            if old_level < row.level <= new_level:
                role = message.guild.get_role(int(row.roleId))
                if role is not None:
                    try:
                        await message.author.add_roles(role, reason=f"Reached level {row.level}")
                        rewards.append(role)
                    except discord.HTTPException:
                        pass
        await self._announce(message, config, message.author, new_level, rewards)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelingCog(bot))
