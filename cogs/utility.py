"""Section 22 utility and information commands.

All responses use Components V2. The ``/embed`` command intentionally creates a
styled Components V2 panel rather than a legacy Discord embed.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from ui.containers import error, information, success
from ui.help_menu import build_help_view, send_help

logger = logging.getLogger(__name__)
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _stamp(value: datetime | None) -> str:
    return f"<t:{int((value or datetime.now(timezone.utc)).timestamp())}:F>"


def _parse_color(value: str | None) -> int:
    if not value:
        return 0xE62334
    if not _HEX.fullmatch(value.strip()):
        raise ValueError("Color must be a six-digit hexadecimal value such as `#E62334`.")
    return int(value.strip().lstrip("#"), 16)


def _channel_name(channel: discord.abc.GuildChannel | None) -> str:
    return channel.mention if channel is not None else "Unknown channel"


class PollView(discord.ui.LayoutView):
    """Interactive in-memory quick poll using Components V2 buttons."""

    def __init__(self, question: str, options: list[str]) -> None:
        super().__init__(timeout=900)
        self.question = question
        self.options = options
        self.votes: dict[int, set[int]] = defaultdict(set)
        self._build()

    def _build(self) -> None:
        result = "\n".join(
            f"**{index + 1}. {option}** — `{len(self.votes[index])}` vote(s)"
            for index, option in enumerate(self.options)
        )
        self.clear_items()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("📊  **Quick Poll**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"**{self.question}**\n\n{result}"),
                accent_color=0xE62334,
            )
        )
        buttons = []
        for index, option in enumerate(self.options):
            button = discord.ui.Button(
                label=option[:80],
                style=discord.ButtonStyle.primary,
                custom_id=f"utility:poll:{id(self)}:{index}",
            )
            button.callback = self._callback(index)
            buttons.append(button)
        self.add_item(discord.ui.ActionRow(*buttons))

    def _callback(self, option_index: int):
        async def callback(interaction: discord.Interaction) -> None:
            user_id = interaction.user.id
            for voters in self.votes.values():
                voters.discard(user_id)
            self.votes[option_index].add(user_id)
            self._build()
            await interaction.response.edit_message(view=self)

        return callback


class UtilityCog(commands.Cog):
    """General information, moderation-adjacent, and convenience commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._deleted: dict[int, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=10))
        self._edited: dict[int, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=10))

    @app_commands.command(name="help", description="Browse BypassX commands.")
    async def help_slash(self, interaction: discord.Interaction) -> None:
        await send_help(interaction, self.bot)

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context) -> None:
        await ctx.send(view=build_help_view(self.bot))

    @app_commands.command(name="userinfo", description="Show detailed information about a user.")
    @app_commands.describe(user="The user to inspect.")
    async def userinfo(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        member = user or interaction.user
        text = (
            f"**User**  {member.mention} (`{member.id}`)\n"
            f"**Name**  `{member}`\n"
            f"**Created**  {_stamp(member.created_at)}\n"
            f"**Bot**  `{'yes' if member.bot else 'no'}`"
        )
        if isinstance(member, discord.Member):
            roles = ", ".join(role.mention for role in member.roles[1:]) or "None"
            text += f"\n**Joined**  {_stamp(member.joined_at)}\n**Roles**  {roles}"
        await interaction.response.send_message(**information("User Information", text), ephemeral=True)

    @app_commands.command(name="serverinfo", description="Show a full overview of this server.")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        text = (
            f"**Server**  `{guild.name}` (`{guild.id}`)\n"
            f"**Owner**  <@{guild.owner_id}>\n"
            f"**Created**  {_stamp(guild.created_at)}\n"
            f"**Members**  `{guild.member_count or 0}`\n"
            f"**Channels**  `{len(guild.channels)}`\n"
            f"**Roles**  `{len(guild.roles)}`\n"
            f"**Boosts**  `{guild.premium_subscription_count}` · level `{guild.premium_tier}`\n"
            f"**Verification**  `{guild.verification_level.name}`"
        )
        await interaction.response.send_message(**information("Server Information", text), ephemeral=True)

    @app_commands.command(name="avatar", description="Display a user's full-size avatar link.")
    @app_commands.describe(user="The user whose avatar to display.")
    async def avatar(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        member = user or interaction.user
        avatar = member.display_avatar.replace(size=4096)
        await interaction.response.send_message(**information("Avatar", f"{member.mention}\n[Open full-size avatar]({avatar.url})"), ephemeral=True)

    @app_commands.command(name="banner", description="Display a user's or server's banner link.")
    @app_commands.describe(user="Leave empty for the server banner; provide a user for their banner.")
    async def banner(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        if user is not None:
            fetched = user if user.banner is not None else await self.bot.fetch_user(user.id)
            banner = fetched.banner
            title = f"{user}'s Banner"
        else:
            if interaction.guild is None:
                await interaction.response.send_message(**error("Provide a user when using this command outside a server."), ephemeral=True)
                return
            guild = interaction.guild
            banner = guild.banner
            title = f"{guild.name}'s Banner"
        if banner is None:
            await interaction.response.send_message(**information(title, "No banner is available."), ephemeral=True)
            return
        await interaction.response.send_message(**information(title, f"[Open banner]({banner.replace(size=4096).url})"), ephemeral=True)

    @app_commands.command(name="roleinfo", description="Show details about a server role.")
    @app_commands.describe(role="The role to inspect.")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role) -> None:
        text = f"**Role**  {role.mention} (`{role.id}`)\n**Position**  `{role.position}`\n**Color**  `{role.color}`\n**Members**  `{len(role.members)}`\n**Mentionable**  `{role.mentionable}`\n**Managed**  `{role.managed}`"
        await interaction.response.send_message(**information("Role Information", text), ephemeral=True)

    @app_commands.command(name="channelinfo", description="Show details about a text channel.")
    @app_commands.describe(channel="The channel to inspect.")
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        text = f"**Channel**  {channel.mention} (`{channel.id}`)\n**Type**  `{channel.type.name}`\n**Category**  `{channel.category.name if channel.category else 'None'}`\n**Position**  `{channel.position}`\n**Created**  {_stamp(channel.created_at)}\n**Slowmode**  `{channel.slowmode_delay}s`"
        await interaction.response.send_message(**information("Channel Information", text), ephemeral=True)

    @app_commands.command(name="ping", description="Check bot latency and API status.")
    async def ping(self, interaction: discord.Interaction) -> None:
        websocket = round(self.bot.latency * 1000) if self.bot.latency != float("inf") else -1
        await interaction.response.send_message(**success(f"Gateway latency: `{websocket}ms`. API connection is operational."), ephemeral=True)

    @app_commands.command(name="snipe", description="Show the most recently deleted message in this channel.")
    async def snipe(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None or not self._deleted[interaction.channel_id]:
            await interaction.response.send_message(**information("Snipe", "No deleted message is cached for this channel."), ephemeral=True)
            return
        item = self._deleted[interaction.channel_id][-1]
        await interaction.response.send_message(**information("Deleted Message", self._message_text(item)), ephemeral=True)

    @app_commands.command(name="editsnipe", description="Show the most recently edited message in this channel.")
    async def editsnipe(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None or not self._edited[interaction.channel_id]:
            await interaction.response.send_message(**information("Edit Snipe", "No edited message is cached for this channel."), ephemeral=True)
            return
        item = self._edited[interaction.channel_id][-1]
        await interaction.response.send_message(**information("Edited Message", self._message_text(item)), ephemeral=True)

    @staticmethod
    def _message_text(item: dict[str, Any]) -> str:
        return f"**Author**  {item['author']} (`{item['author_id']}`)\n**Before**  {item.get('before', item.get('content', ''))[:1500]}\n**After**  {item.get('after', item.get('content', ''))[:1500]}\n**Time**  {_stamp(item['time'])}"

    @app_commands.command(name="poll", description="Create a quick button poll with up to five options.")
    @app_commands.describe(question="The poll question.", options="Pipe-separated options, for example: Yes | No | Maybe.")
    @require_tier(1)
    async def poll(self, interaction: discord.Interaction, question: str, options: str) -> None:
        choices = [choice.strip() for choice in options.split("|") if choice.strip()]
        if not question.strip() or not 2 <= len(choices) <= 5:
            await interaction.response.send_message(**error("Provide a question and between 2 and 5 pipe-separated options."), ephemeral=True)
            return
        await interaction.response.send_message(view=PollView(question[:300], [choice[:80] for choice in choices]))

    @app_commands.command(name="embed", description="Build and send a styled Components V2 information panel.")
    @app_commands.describe(title="Panel title.", message="Panel body.", color="Optional six-digit hex color.", channel="Destination channel.")
    @require_tier(2)
    async def embed(self, interaction: discord.Interaction, title: str, message: str, color: str | None = None, channel: discord.TextChannel | None = None) -> None:
        try:
            accent = _parse_color(color)
        except ValueError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        destination = channel or interaction.channel
        if not hasattr(destination, "send"):
            await interaction.response.send_message(**error("Choose a text channel."), ephemeral=True)
            return
        view = discord.ui.LayoutView(timeout=180)
        view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"**{title[:256]}**"), discord.ui.Separator(), discord.ui.TextDisplay(message[:4000]), accent_color=accent))
        await destination.send(view=view)
        await interaction.response.send_message(**success(f"Panel sent to {_channel_name(destination)}."), ephemeral=True)

    @app_commands.command(name="say", description="Send a structured message through BypassX.")
    @app_commands.describe(message="Message body.", channel="Destination channel.")
    @require_tier(2)
    async def say(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel | None = None) -> None:
        destination = channel or interaction.channel
        if not hasattr(destination, "send"):
            await interaction.response.send_message(**error("Choose a text channel."), ephemeral=True)
            return
        await destination.send(view=information("BypassX", message[:4000])["view"])
        await interaction.response.send_message(**success(f"Message sent to {_channel_name(destination)}."), ephemeral=True)

    @app_commands.command(name="inviteinfo", description="Inspect a Discord invite.")
    @app_commands.describe(invite="Invite URL or invite code.")
    async def inviteinfo(self, interaction: discord.Interaction, invite: str) -> None:
        try:
            result = await self.bot.fetch_invite(invite.strip(), with_counts=True, with_expiration=True)
        except (discord.NotFound, discord.HTTPException, discord.Forbidden):
            await interaction.response.send_message(**error("That invite could not be found or accessed."), ephemeral=True)
            return
        guild_name = result.guild.name if result.guild else "Unknown server"
        channel_name = result.channel.name if result.channel else "Unknown channel"
        text = f"**Server**  `{guild_name}`\n**Channel**  `{channel_name}`\n**Members**  `{result.approximate_member_count or 'Unknown'}`\n**Online**  `{result.approximate_presence_count or 'Unknown'}`\n**Code**  `{result.code}`"
        await interaction.response.send_message(**information("Invite Information", text), ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        self._deleted[message.channel.id].append({"author": str(message.author), "author_id": message.author.id, "content": message.content or "[no text]", "time": datetime.now(timezone.utc)})

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or before.guild is None or before.content == after.content:
            return
        self._edited[before.channel.id].append({"author": str(before.author), "author_id": before.author.id, "before": before.content or "[no text]", "after": after.content or "[no text]", "time": datetime.now(timezone.utc)})


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
