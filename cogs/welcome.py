"""Welcome, farewell, and autorole features.

Category    : Welcome
Emoji       : bx_wave
Color       : #1ABC9C
Description : Configure member greetings and automatic role assignment.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from db.queries.welcome import get_welcome_config, upsert_welcome_config
from ui.containers import error, information, success

WELCOME_ACCENT = 0xE62334


class WelcomeCog(commands.Cog):
    """Manage welcome/farewell messages and autoroles."""

    welcome = app_commands.Group(name="welcome", description="Configure welcome messages.")
    farewell = app_commands.Group(name="farewell", description="Configure farewell messages.")
    autorole = app_commands.Group(name="autorole", description="Configure automatic member roles.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    @staticmethod
    def _guild(interaction: discord.Interaction) -> discord.Guild | None:
        return interaction.guild

    @staticmethod
    def _render(template: str | None, member: discord.Member, guild: discord.Guild) -> str:
        """Expand the documented welcome/farewell variables."""
        text = template or "Welcome to {server}, {user}!"
        replacements = {
            "{user}": member.mention,
            "{username}": member.name,
            "{server}": guild.name,
            "{membercount}": str(guild.member_count or len(guild.members)),
            "{id}": str(member.id),
        }
        for variable, value in replacements.items():
            text = text.replace(variable, value)
        return text

    @staticmethod
    def _card_payload(title: str, message: str) -> dict:
        """Build a Components V2 greeting card without requiring a binary asset."""
        return information(title, message, accent=WELCOME_ACCENT)

    async def _configured_channel(self, guild: discord.Guild, channel_id: str | None) -> discord.TextChannel | None:
        if not channel_id:
            return None
        channel = guild.get_channel(int(channel_id))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_greeting(
        self,
        guild: discord.Guild,
        member: discord.Member,
        channel_id: str | None,
        template: str | None,
        card: bool,
        title: str,
    ) -> bool:
        channel = await self._configured_channel(guild, channel_id)
        if channel is None:
            return False
        message = self._render(template, member, guild)
        payload = self._card_payload(title, message) if card else {"view": information(title, message, accent=WELCOME_ACCENT)["view"]}
        try:
            await channel.send(**payload)
        except (discord.Forbidden, discord.HTTPException):
            return False
        return True

    @welcome.command(name="channel", description="Set the welcome message channel.")
    @app_commands.describe(channel="Channel where welcome messages are sent.")
    @require_tier(2)
    async def welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_welcome_config(self.db, str(guild.id), welcomeChannel=str(channel.id))
        await interaction.response.send_message(**success(f"Welcome messages will be sent to {channel.mention}."), ephemeral=True)

    @welcome.command(name="message", description="Set the welcome message text.")
    @app_commands.describe(message="Message text. Variables: {user}, {username}, {server}, {membercount}, {id}.")
    @require_tier(2)
    async def welcome_message(self, interaction: discord.Interaction, message: str) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        message = message.strip()
        if not message or len(message) > 2000:
            await interaction.response.send_message(**error("Welcome messages must contain 1–2000 characters."), ephemeral=True)
            return
        await upsert_welcome_config(self.db, str(guild.id), welcomeMessage=message)
        await interaction.response.send_message(**success("Welcome message updated."), ephemeral=True)

    @welcome.command(name="card", description="Toggle the welcome card layout on or off.")
    @app_commands.describe(enabled="Whether the welcome card layout is enabled.")
    @require_tier(2)
    async def welcome_card(self, interaction: discord.Interaction, enabled: bool) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_welcome_config(self.db, str(guild.id), welcomeCard=enabled)
        await interaction.response.send_message(**success(f"Welcome card layout {'enabled' if enabled else 'disabled'}."), ephemeral=True)

    @welcome.command(name="test", description="Preview the current welcome message.")
    @require_tier(2)
    async def welcome_test(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(**error("This command requires a server member."), ephemeral=True)
            return
        config = await get_welcome_config(self.db, str(guild.id))
        if config is None:
            await interaction.response.send_message(**error("Welcome messages are not configured yet."), ephemeral=True)
            return
        text = self._render(config.welcomeMessage, interaction.user, guild)
        await interaction.response.send_message(**self._card_payload("Welcome Preview", text), ephemeral=True)

    @farewell.command(name="channel", description="Set the farewell message channel.")
    @app_commands.describe(channel="Channel where farewell messages are sent.")
    @require_tier(2)
    async def farewell_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_welcome_config(self.db, str(guild.id), farewellChannel=str(channel.id))
        await interaction.response.send_message(**success(f"Farewell messages will be sent to {channel.mention}."), ephemeral=True)

    @farewell.command(name="message", description="Set the farewell message text.")
    @app_commands.describe(message="Message text. Variables: {user}, {username}, {server}, {membercount}, {id}.")
    @require_tier(2)
    async def farewell_message(self, interaction: discord.Interaction, message: str) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        message = message.strip()
        if not message or len(message) > 2000:
            await interaction.response.send_message(**error("Farewell messages must contain 1–2000 characters."), ephemeral=True)
            return
        await upsert_welcome_config(self.db, str(guild.id), farewellMessage=message)
        await interaction.response.send_message(**success("Farewell message updated."), ephemeral=True)

    @farewell.command(name="test", description="Preview the current farewell message.")
    @require_tier(2)
    async def farewell_test(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(**error("This command requires a server member."), ephemeral=True)
            return
        config = await get_welcome_config(self.db, str(guild.id))
        if config is None:
            await interaction.response.send_message(**error("Farewell messages are not configured yet."), ephemeral=True)
            return
        text = self._render(config.farewellMessage, interaction.user, guild)
        await interaction.response.send_message(**self._card_payload("Farewell Preview", text), ephemeral=True)

    @autorole.command(name="add", description="Add a role granted to members when they join.")
    @app_commands.describe(role="Role granted to human members on join.")
    @require_tier(2)
    async def autorole_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        config = await get_welcome_config(self.db, str(guild.id))
        roles = list(config.autoRoles) if config else []
        if str(role.id) not in roles:
            roles.append(str(role.id))
        await upsert_welcome_config(self.db, str(guild.id), autoRoles=roles[:25])
        await interaction.response.send_message(**success(f"Added {role.mention} as a member autorole."), ephemeral=True)

    @autorole.command(name="remove", description="Remove an autorole.")
    @app_commands.describe(role="Role to remove from the member autorole list.")
    @require_tier(2)
    async def autorole_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        config = await get_welcome_config(self.db, str(guild.id))
        roles = [role_id for role_id in (list(config.autoRoles) if config else []) if role_id != str(role.id)]
        await upsert_welcome_config(self.db, str(guild.id), autoRoles=roles)
        await interaction.response.send_message(**success(f"Removed {role.mention} from the member autorole list."), ephemeral=True)

    @autorole.command(name="list", description="View all configured autoroles.")
    @require_tier(2)
    async def autorole_list(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        config = await get_welcome_config(self.db, str(guild.id))
        member_roles = " ".join(f"<@&{role_id}>" for role_id in (list(config.autoRoles) if config else [])) or "None"
        bot_roles = " ".join(f"<@&{role_id}>" for role_id in (list(config.botAutoRoles) if config else [])) or "None"
        await interaction.response.send_message(**information("Autoroles", f"**Members**  {member_roles}\n**Bots**  {bot_roles}", accent=WELCOME_ACCENT), ephemeral=True)

    @autorole.command(name="bot", description="Set a role given exclusively to bots when they join.")
    @app_commands.describe(role="Role granted to bots on join.")
    @require_tier(2)
    async def autorole_bot(self, interaction: discord.Interaction, role: discord.Role) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_welcome_config(self.db, str(guild.id), botAutoRoles=[str(role.id)])
        await interaction.response.send_message(**success(f"{role.mention} will be granted exclusively to bots on join."), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        config = await get_welcome_config(self.db, str(member.guild.id))
        if config is None:
            return
        role_ids = list(config.botAutoRoles if member.bot else config.autoRoles)
        for role_id in role_ids:
            role = member.guild.get_role(int(role_id))
            if role is None:
                continue
            try:
                await member.add_roles(role, reason="Configured autorole on member join")
            except (discord.Forbidden, discord.HTTPException):
                continue
        if not member.bot:
            await self._send_greeting(member.guild, member, config.welcomeChannel, config.welcomeMessage, config.welcomeCard, "Welcome")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        config = await get_welcome_config(self.db, str(member.guild.id))
        if config is None:
            return
        await self._send_greeting(member.guild, member, config.farewellChannel, config.farewellMessage, False, "Farewell")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
