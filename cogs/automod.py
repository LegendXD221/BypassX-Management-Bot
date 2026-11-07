"""AutoMod Cog.

Category    : AutoMod
Emoji       : bx_bolt
Color       : #EB459E
Description : Automated spam, raid, content, and account-age protection.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from db.queries.automod import get_automod_config, upsert_automod_config
from ui.containers import error, information, success

logger = logging.getLogger(__name__)

_LINK_PATTERN = re.compile(r"(?:https?://|www\.|discord(?:\.gg|\.com/invite)/)\S+", re.I)
_EVENT_CHOICES = [
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove"),
]


class AutomodCog(commands.Cog):
    """Configure and enforce database-backed AutoMod rules."""

    automod = app_commands.Group(name="automod", description="Configure automated moderation.")
    filter = app_commands.Group(name="filter", description="Manage filtered words and phrases.", parent=automod)
    exempt = app_commands.Group(name="exempt", description="Manage AutoMod exemptions.", parent=automod)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self._spam: defaultdict[tuple[int, int, int], deque[datetime]] = defaultdict(deque)
        self._joins: defaultdict[int, deque[datetime]] = defaultdict(deque)

    async def _guild_required(self, interaction: discord.Interaction) -> discord.Guild | None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return None
        return interaction.guild

    async def _current(self, guild_id: int):
        return await get_automod_config(self.db, str(guild_id))

    @automod.command(name="enable", description="Enable the AutoMod module.")
    @require_tier(2)
    async def enable(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), enabled=True)
        await interaction.response.send_message(**success("AutoMod enabled."), ephemeral=True)

    @automod.command(name="disable", description="Disable the AutoMod module.")
    @require_tier(2)
    async def disable(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), enabled=False)
        await interaction.response.send_message(**success("AutoMod disabled."), ephemeral=True)

    @automod.command(name="antispam", description="Configure the spam detection threshold.")
    @app_commands.describe(threshold="Messages in the rolling window required to trigger spam protection.")
    @require_tier(2)
    async def antispam(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 2, 20]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), antiSpam=True, spamThreshold=int(threshold))
        await interaction.response.send_message(**success(f"Anti-spam enabled at `{threshold}` messages per window."), ephemeral=True)

    @automod.command(name="antiraid", description="Configure raid detection sensitivity.")
    @app_commands.describe(threshold="New members in 60 seconds required to trigger raid protection.")
    @require_tier(2)
    async def antiraid(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 2, 50]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), antiRaid=True, raidThreshold=int(threshold))
        await interaction.response.send_message(**success(f"Anti-raid enabled at `{threshold}` joins per minute."), ephemeral=True)

    @filter.command(name="add", description="Add a word or phrase to the filter list.")
    @app_commands.describe(phrase="Word or phrase to block.")
    @require_tier(2)
    async def filter_add(self, interaction: discord.Interaction, phrase: str) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        phrase = phrase.strip().lower()
        config = await self._current(guild.id)
        words = list(config.filterWords) if config else []
        if not phrase or len(phrase) > 100:
            await interaction.response.send_message(**error("The filtered phrase must contain 1–100 characters."), ephemeral=True)
            return
        if phrase not in words:
            words.append(phrase)
        await upsert_automod_config(self.db, str(guild.id), filterEnabled=True, filterWords=words[:500])
        await interaction.response.send_message(**success(f"Added `{phrase}` to the filter list."), ephemeral=True)

    @filter.command(name="remove", description="Remove a word or phrase from the filter.")
    @app_commands.describe(phrase="Word or phrase to remove.")
    @require_tier(2)
    async def filter_remove(self, interaction: discord.Interaction, phrase: str) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        phrase = phrase.strip().lower()
        config = await self._current(guild.id)
        words = list(config.filterWords) if config else []
        if phrase not in words:
            await interaction.response.send_message(**error("That phrase is not in the filter list."), ephemeral=True)
            return
        words.remove(phrase)
        await upsert_automod_config(self.db, str(guild.id), filterEnabled=bool(words), filterWords=words)
        await interaction.response.send_message(**success(f"Removed `{phrase}` from the filter list."), ephemeral=True)

    @filter.command(name="list", description="View all filtered words and phrases.")
    @require_tier(2)
    async def filter_list(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await self._current(guild.id)
        words = list(config.filterWords) if config else []
        body = "\n".join(f"• `{word}`" for word in words) or "No filtered phrases configured."
        await interaction.response.send_message(**information("AutoMod Filter", body, accent=0xE62334), ephemeral=True)

    @filter.command(name="clear", description="Clear the entire word filter.")
    @require_tier(2)
    async def filter_clear(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), filterEnabled=False, filterWords=[])
        await interaction.response.send_message(**success("Cleared the AutoMod filter."), ephemeral=True)

    @automod.command(name="caps", description="Toggle excessive-caps detection.")
    @app_commands.describe(enabled="Whether excessive-caps detection is enabled.", threshold="Uppercase percentage required to trigger.")
    @require_tier(2)
    async def caps(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        threshold: app_commands.Range[int, 50, 100] = 70,
    ) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), capsEnabled=enabled, capsThreshold=int(threshold))
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(**success(f"Excessive-caps detection {state} at `{threshold}%`."), ephemeral=True)

    @automod.command(name="links", description="Configure link and invite filtering.")
    @app_commands.describe(enabled="Whether links and Discord invites should be blocked.")
    @require_tier(2)
    async def links(self, interaction: discord.Interaction, enabled: bool) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), linksEnabled=enabled)
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(**success(f"Link and invite filtering {state}."), ephemeral=True)

    @automod.command(name="mentions", description="Set the mass-mention threshold.")
    @app_commands.describe(threshold="Mentions in one message required to trigger protection.")
    @require_tier(2)
    async def mentions(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 2, 50]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), mentionsEnabled=True, mentionThreshold=int(threshold))
        await interaction.response.send_message(**success(f"Mention protection enabled at `{threshold}` mentions."), ephemeral=True)

    @automod.command(name="newaccount", description="Set the minimum account age for messages.")
    @app_commands.describe(days="Accounts younger than this many days will be blocked; 0 disables it.")
    @require_tier(2)
    async def newaccount(self, interaction: discord.Interaction, days: app_commands.Range[int, 0, 365]) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        await upsert_automod_config(self.db, str(guild.id), newAccountAge=int(days))
        state = "disabled" if days == 0 else f"set to `{days}` days"
        await interaction.response.send_message(**success(f"New-account protection {state}."), ephemeral=True)

    @exempt.command(name="role", description="Add or remove a role AutoMod exemption.")
    @app_commands.describe(action="Add or remove the exemption.", role="Role to update.")
    @app_commands.choices(action=_EVENT_CHOICES)
    @require_tier(2)
    async def exempt_role(self, interaction: discord.Interaction, action: app_commands.Choice[str], role: discord.Role) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await self._current(guild.id)
        roles = list(config.exemptRoles) if config else []
        role_id = str(role.id)
        if action.value == "add" and role_id not in roles:
            roles.append(role_id)
        elif action.value == "remove":
            roles = [value for value in roles if value != role_id]
        await upsert_automod_config(self.db, str(guild.id), exemptRoles=roles[:100])
        await interaction.response.send_message(**success(f"{role.mention} exemption {action.name.lower()}."), ephemeral=True)

    @exempt.command(name="channel", description="Add or remove a channel AutoMod exemption.")
    @app_commands.describe(action="Add or remove the exemption.", channel="Channel to update.")
    @app_commands.choices(action=_EVENT_CHOICES)
    @require_tier(2)
    async def exempt_channel(self, interaction: discord.Interaction, action: app_commands.Choice[str], channel: discord.TextChannel) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await self._current(guild.id)
        channels = list(config.exemptChannels) if config else []
        channel_id = str(channel.id)
        if action.value == "add" and channel_id not in channels:
            channels.append(channel_id)
        elif action.value == "remove":
            channels = [value for value in channels if value != channel_id]
        await upsert_automod_config(self.db, str(guild.id), exemptChannels=channels[:100])
        await interaction.response.send_message(**success(f"{channel.mention} exemption {action.name.lower()}."), ephemeral=True)

    @automod.command(name="view", description="View the full AutoMod configuration.")
    @require_tier(2)
    async def view(self, interaction: discord.Interaction) -> None:
        guild = await self._guild_required(interaction)
        if guild is None:
            return
        config = await self._current(guild.id)
        if config is None:
            await interaction.response.send_message(**information("AutoMod Configuration", "AutoMod is disabled and has no custom rules.", accent=0xE62334), ephemeral=True)
            return
        body = (
            f"**Module**  {'enabled' if config.enabled else 'disabled'}\n"
            f"**Anti-spam**  {'on' if config.antiSpam else 'off'} · threshold `{config.spamThreshold}`\n"
            f"**Anti-raid**  {'on' if config.antiRaid else 'off'} · threshold `{config.raidThreshold}` joins/minute\n"
            f"**Filter**  {'on' if config.filterEnabled else 'off'} · `{len(config.filterWords)}` phrases\n"
            f"**Caps**  {'on' if config.capsEnabled else 'off'} · threshold `{config.capsThreshold}%`\n"
            f"**Links**  {'on' if config.linksEnabled else 'off'}\n"
            f"**Mentions**  {'on' if config.mentionsEnabled else 'off'} · threshold `{config.mentionThreshold}`\n"
            f"**New accounts**  `{config.newAccountAge}` days\n"
            f"**Exemptions**  `{len(config.exemptRoles)}` roles · `{len(config.exemptChannels)}` channels"
        )
        await interaction.response.send_message(**information("AutoMod Configuration", body, accent=0xE62334), ephemeral=True)

    async def _is_exempt(self, message: discord.Message, config) -> bool:
        if str(message.channel.id) in config.exemptChannels:
            return True
        return any(str(role.id) in config.exemptRoles for role in getattr(message.author, "roles", ()))

    async def _log_violation(self, message: discord.Message, reason: str) -> None:
        logging_cog = self.bot.get_cog("LoggingCog")
        if logging_cog is not None and hasattr(logging_cog, "_emit"):
            await logging_cog._emit(
                message.guild,
                "mod_actions",
                f"**Action**  AutoMod message removal\n**Member**  {message.author.mention}\n**Channel**  {message.channel.mention}\n**Reason**  {reason}",
                accent=0xE62334,
            )

    def _spam_triggered(self, message: discord.Message, threshold: int) -> bool:
        key = (message.guild.id, message.author.id, message.channel.id)
        now = datetime.now(timezone.utc)
        history = self._spam[key]
        while history and now - history[0] > timedelta(seconds=8):
            history.popleft()
        history.append(now)
        if len(history) >= threshold:
            history.clear()
            return True
        return False

    def _raid_triggered(self, guild_id: int, threshold: int) -> bool:
        now = datetime.now(timezone.utc)
        history = self._joins[guild_id]
        while history and now - history[0] > timedelta(seconds=60):
            history.popleft()
        history.append(now)
        return len(history) >= threshold

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        config = await self._current(message.guild.id)
        if config is None or not config.enabled or await self._is_exempt(message, config):
            return

        content = message.content
        reason: str | None = None
        if config.filterEnabled and any(phrase in content.lower() for phrase in config.filterWords):
            reason = "filtered word or phrase"
        elif config.linksEnabled and _LINK_PATTERN.search(content):
            reason = "link or invite"
        elif config.mentionsEnabled and len(message.mentions) + len(message.role_mentions) >= config.mentionThreshold:
            reason = "mass mentions"
        elif config.capsEnabled:
            letters = [char for char in content if char.isalpha()]
            if len(letters) >= 8 and sum(char.isupper() for char in letters) * 100 / len(letters) >= config.capsThreshold:
                reason = "excessive capitals"
        elif config.newAccountAge:
            age_days = (datetime.now(timezone.utc) - message.author.created_at).total_seconds() / 86400
            if age_days < config.newAccountAge:
                reason = "new account"
        if reason is None and config.antiSpam and self._spam_triggered(message, config.spamThreshold):
            reason = "spam threshold"

        if reason is None:
            return
        try:
            await message.delete(reason=f"AutoMod: {reason}")
        except discord.HTTPException:
            logger.debug("AutoMod could not delete message %s", message.id, exc_info=True)
        await self._log_violation(message, reason)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        config = await self._current(member.guild.id)
        if config is None or not config.enabled or not config.antiRaid:
            return
        if not self._raid_triggered(member.guild.id, config.raidThreshold):
            return
        try:
            await member.kick(reason="AutoMod raid protection")
        except discord.HTTPException:
            logger.debug("AutoMod could not remove raid member %s", member.id, exc_info=True)
        logging_cog = self.bot.get_cog("LoggingCog")
        if logging_cog is not None and hasattr(logging_cog, "_emit"):
            await logging_cog._emit(
                member.guild,
                "mod_actions",
                f"**Action**  AutoMod raid protection\n**Member**  {member.mention}\n**Reason**  `{config.raidThreshold}` joins in 60 seconds",
                accent=0xE62334,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutomodCog(bot))
