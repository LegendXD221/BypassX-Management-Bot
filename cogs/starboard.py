"""Starboard and engagement analytics for BypassX.

Category    : Starboard & Analytics
Emoji       : bx_chart
Color       : #F1C40F
Description : Highlight popular messages and summarize server engagement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config.emojis import E
from core.checks import require_tier
from db.queries.starboard import (
    get_starboard_config,
    get_starboard_message,
    increment_engagement,
    list_engagement_days,
    set_starboard_message_id,
    top_starboard_messages,
    update_star_count,
    upsert_starboard_config,
    upsert_starboard_message,
)
from ui.containers import error, information, success

logger = logging.getLogger(__name__)


def _emoji(value: str) -> str | discord.PartialEmoji:
    value = value.strip()
    if value.startswith("<:") or value.startswith("<a:"):
        parsed = discord.PartialEmoji.from_str(value)
        if parsed.id is None or not parsed.name:
            raise ValueError("Use a valid custom emoji such as <:name:123456789012345678>.")
        return parsed
    if not value or len(value) > 16 or any(character.isspace() for character in value):
        raise ValueError("Use one Unicode emoji or a valid custom emoji.")
    return value


def _emoji_matches(value: str, reaction: discord.Reaction | discord.PartialEmoji) -> bool:
    current = reaction.emoji if isinstance(reaction, discord.Reaction) else reaction
    if value.startswith("<:") or value.startswith("<a:"):
        stored = discord.PartialEmoji.from_str(value)
        return stored.id == current.id
    return str(current) == value


def _day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class StarboardMessageView(discord.ui.LayoutView):
    """Components V2 mirror used for a starboard entry."""

    def __init__(self, message: discord.Message, stars: int, emoji: str) -> None:
        super().__init__(timeout=None)
        content = message.content.strip() or "[No text content]"
        if len(content) > 1800:
            content = content[:1797] + "..."
        attachments = "\n".join(attachment.url for attachment in message.attachments[:5])
        details = (
            f"{emoji}  **{stars} star(s)**\n"
            f"**Author**  {message.author.mention}\n"
            f"**Source**  [Jump to message]({message.jump_url})\n\n"
            f"{content}"
        )
        if attachments:
            details += f"\n\n**Attachments**\n{attachments}"
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{E.bx_chart}  **BypassX Starboard**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(details),
                accent_color=0xF1C40F,
            )
        )


class StarboardCog(commands.Cog):
    """Manage popular-message highlights and lightweight engagement analytics."""

    starboard = app_commands.Group(name="starboard", description="Configure the popular-message starboard.")
    analytics = app_commands.Group(name="analytics", description="View server engagement analytics.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    async def _guild(self, interaction: discord.Interaction) -> discord.Guild | None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return None
        return interaction.guild

    async def _star_count(self, message: discord.Message, config: Any) -> int:
        matching = next((reaction for reaction in message.reactions if _emoji_matches(config.emoji, reaction)), None)
        if matching is None:
            return 0
        count = matching.count
        if not config.allowSelfStar and count:
            try:
                async for user in matching.users():
                    if user.id == message.author.id:
                        count -= 1
                        break
            except discord.HTTPException:
                pass
        return max(0, count)

    async def _refresh_starboard(self, message: discord.Message, config: Any) -> None:
        if message.guild is None or message.author.bot:
            return
        if str(message.channel.id) in (config.ignoredChannels or []):
            return
        count = await self._star_count(message, config)
        record = await get_starboard_message(self.db, str(message.guild.id), str(message.id))
        if record is None and count < config.threshold:
            return
        if record is None:
            attachment_urls = [attachment.url for attachment in message.attachments[:10]]
            record = await upsert_starboard_message(
                self.db,
                str(message.guild.id),
                str(message.id),
                sourceChannelId=str(message.channel.id),
                authorId=str(message.author.id),
                content=message.content[:4000],
                attachmentUrls=attachment_urls,
                stars=count,
            )
        else:
            await update_star_count(self.db, record.id, count)
            record.stars = count
        channel = message.guild.get_channel(int(config.channelId)) if config.channelId else None
        if not isinstance(channel, discord.TextChannel):
            return
        if count < config.threshold and record.starboardMessageId:
            try:
                old = await channel.fetch_message(int(record.starboardMessageId))
                await old.delete(reason="Starboard threshold no longer met")
            except (discord.NotFound, discord.HTTPException):
                pass
            return
        if count < config.threshold:
            return
        view = StarboardMessageView(message, count, config.emoji)
        if record.starboardMessageId:
            try:
                old = await channel.fetch_message(int(record.starboardMessageId))
                await old.edit(view=view)
                return
            except (discord.NotFound, discord.HTTPException):
                pass
        try:
            mirrored = await channel.send(view=view)
            await set_starboard_message_id(self.db, record.id, str(mirrored.id))
        except discord.HTTPException:
            logger.exception("Could not publish starboard message for %s", message.id)

    @starboard.command(name="setup", description="Enable the starboard in a channel.")
    @app_commands.describe(channel="Destination channel.", threshold="Stars required, from 1 to 50.")
    @require_tier(2)
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel, threshold: app_commands.Range[int, 1, 50] = 3) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        config = await upsert_starboard_config(self.db, str(guild.id), enabled=True, channelId=str(channel.id), threshold=int(threshold))
        await interaction.response.send_message(**success(f"Starboard enabled in {channel.mention} at `{config.threshold}` star(s)."), ephemeral=True)

    @starboard.command(name="threshold", description="Change the number of stars required.")
    @app_commands.describe(threshold="Stars required, from 1 to 50.")
    @require_tier(2)
    async def threshold(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 1, 50]) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        await upsert_starboard_config(self.db, str(guild.id), threshold=int(threshold))
        await interaction.response.send_message(**success(f"Starboard threshold set to `{threshold}` star(s)."), ephemeral=True)

    @starboard.command(name="emoji", description="Set the emoji used for starboard reactions.")
    @app_commands.describe(emoji="Unicode or custom emoji.")
    @require_tier(2)
    async def emoji(self, interaction: discord.Interaction, emoji: str) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        try:
            normalized = str(_emoji(emoji))
        except ValueError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        await upsert_starboard_config(self.db, str(guild.id), emoji=normalized)
        await interaction.response.send_message(**success(f"Starboard emoji set to {normalized}."), ephemeral=True)

    @starboard.command(name="selfstar", description="Allow or disallow authors from starring their own messages.")
    @app_commands.describe(allowed="Whether the message author counts their own star.")
    @require_tier(2)
    async def selfstar(self, interaction: discord.Interaction, allowed: bool) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        await upsert_starboard_config(self.db, str(guild.id), allowSelfStar=allowed)
        await interaction.response.send_message(**success(f"Self-stars are now {'allowed' if allowed else 'ignored'}."), ephemeral=True)

    @starboard.command(name="ignore", description="Ignore or unignore a channel from starboard tracking.")
    @app_commands.describe(channel="Channel to toggle.")
    @require_tier(2)
    async def ignore(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        config = await get_starboard_config(self.db, str(guild.id))
        ignored = list(config.ignoredChannels if config else [])
        channel_id = str(channel.id)
        if channel_id in ignored:
            ignored.remove(channel_id)
            message = f"Starboard tracking resumed in {channel.mention}."
        else:
            ignored.append(channel_id)
            message = f"Starboard tracking ignored in {channel.mention}."
        await upsert_starboard_config(self.db, str(guild.id), ignoredChannels=ignored[:100])
        await interaction.response.send_message(**success(message), ephemeral=True)

    @starboard.command(name="view", description="View the current starboard configuration.")
    @require_tier(2)
    async def view(self, interaction: discord.Interaction) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        config = await get_starboard_config(self.db, str(guild.id))
        if config is None:
            await interaction.response.send_message(**information("Starboard", "Starboard is not configured."), ephemeral=True)
            return
        channel = f"<#{config.channelId}>" if config.channelId else "not set"
        body = f"**Status**  {'enabled' if config.enabled else 'disabled'}\n**Channel**  {channel}\n**Threshold**  `{config.threshold}`\n**Emoji**  {config.emoji}\n**Self-star**  {'allowed' if config.allowSelfStar else 'ignored'}\n**Ignored channels**  `{len(config.ignoredChannels or [])}`"
        await interaction.response.send_message(**information("Starboard Configuration", body), ephemeral=True)

    @starboard.command(name="disable", description="Disable the starboard without deleting historical records.")
    @require_tier(2)
    async def disable(self, interaction: discord.Interaction) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        await upsert_starboard_config(self.db, str(guild.id), enabled=False)
        await interaction.response.send_message(**success("Starboard disabled. Historical analytics were retained."), ephemeral=True)

    @analytics.command(name="overview", description="View recent engagement totals.")
    @app_commands.describe(days="Number of days to summarize, from 1 to 31.")
    @require_tier(1)
    async def overview(self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 31] = 7) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        rows = await list_engagement_days(self.db, str(guild.id), int(days))
        totals = {field: sum(int(getattr(row, field, 0)) for row in rows) for field in ("messages", "reactions", "joins", "leaves", "activeUsers")}
        body = f"**Period**  `{days}` day(s)\n**Messages**  `{totals['messages']}`\n**Reactions**  `{totals['reactions']}`\n**Joins**  `{totals['joins']}`\n**Leaves**  `{totals['leaves']}`\n**Active user events**  `{totals['activeUsers']}`"
        await interaction.response.send_message(**information("Engagement Overview", body), ephemeral=True)

    @analytics.command(name="top", description="View the most-starred messages.")
    @app_commands.describe(limit="Number of entries, from 1 to 10.")
    @require_tier(1)
    async def top(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 10) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        rows = await top_starboard_messages(self.db, str(guild.id), int(limit))
        if not rows:
            await interaction.response.send_message(**information("Top Messages", "No starboard messages have been recorded."), ephemeral=True)
            return
        body = "\n".join(f"`{index}.` **{row.stars}** star(s) · <#{row.sourceChannelId}> · [message](https://discord.com/channels/{guild.id}/{row.sourceChannelId}/{row.sourceMessageId})" for index, row in enumerate(rows, 1))
        await interaction.response.send_message(**information("Top Starboard Messages", body), ephemeral=True)

    @analytics.command(name="reset", description="Delete engagement aggregate data for this server.")
    @require_tier(3)
    async def reset(self, interaction: discord.Interaction) -> None:
        guild = await self._guild(interaction)
        if guild is None:
            return
        result = await self.db.engagementdaily.delete_many(where={"guildId": str(guild.id)})
        count = result if isinstance(result, int) else result.count
        await interaction.response.send_message(**success(f"Deleted `{count}` daily engagement record(s). Starboard messages were retained."), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        try:
            config = await get_starboard_config(self.db, str(message.guild.id))
            if config:
                if str(message.channel.id) not in (config.ignoredChannels or []):
                    await increment_engagement(self.db, str(message.guild.id), day=_day(), field="messages")
                    await increment_engagement(self.db, str(message.guild.id), day=_day(), field="activeUsers")
        except Exception:
            logger.exception("Could not record message engagement for guild %s", message.guild.id)

    async def _reaction_event(self, payload: discord.RawReactionActionEvent, *, adding: bool) -> None:
        if payload.guild_id is None or (self.bot.user and payload.user_id == self.bot.user.id):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        config = await get_starboard_config(self.db, str(guild.id))
        if config is None or not config.enabled:
            return
        source_channel = guild.get_channel(payload.channel_id)
        if source_channel is None or str(payload.channel_id) in (config.ignoredChannels or []):
            return
        try:
            source = await source_channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.HTTPException):
            return
        if not _emoji_matches(config.emoji, payload.emoji):
            return
        if not config.allowSelfStar and source.author.id == payload.user_id:
            return
        await increment_engagement(self.db, str(guild.id), day=_day(), field="reactions")
        await self._refresh_starboard(source, config)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction_event(payload, adding=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction_event(payload, adding=False)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        try:
            if await get_starboard_config(self.db, str(member.guild.id)):
                await increment_engagement(self.db, str(member.guild.id), day=_day(), field="joins")
        except Exception:
            logger.exception("Could not record member join analytics for guild %s", member.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        try:
            if await get_starboard_config(self.db, str(member.guild.id)):
                await increment_engagement(self.db, str(member.guild.id), day=_day(), field="leaves")
        except Exception:
            logger.exception("Could not record member leave analytics for guild %s", member.guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StarboardCog(bot))
