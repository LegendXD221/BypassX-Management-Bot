"""Persistent reaction roles for the BypassX server.

Category    : Reaction Roles
Emoji       : bx_check
Color       : #E62334
Description : Assign roles through reactions, buttons, or a select menu.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config.emojis import E
from core.checks import require_tier
from db.queries.reaction_roles import (
    REACTION_ROLE_MODES,
    create_panel,
    delete_mapping,
    disable_panel,
    get_panel,
    get_panel_for_message,
    list_mappings,
    list_panels,
    set_panel_message,
    upsert_mapping,
)
from ui.containers import error, information, success

logger = logging.getLogger(__name__)

_MODE_CHOICES = [
    app_commands.Choice(name="Reactions", value="reactions"),
    app_commands.Choice(name="Buttons", value="buttons"),
    app_commands.Choice(name="Select menu", value="select"),
]


def _emoji_object(value: str) -> str | discord.PartialEmoji:
    """Convert stored custom markup to a Discord emoji object."""
    if value.startswith("<:") or value.startswith("<a:"):
        return discord.PartialEmoji.from_str(value)
    return value


def _normalize_emoji(value: str) -> str:
    """Validate and normalize a Unicode or custom Discord emoji string."""
    value = value.strip()
    if not value:
        raise ValueError("Emoji cannot be empty.")
    if value.startswith("<:") or value.startswith("<a:"):
        parsed = discord.PartialEmoji.from_str(value)
        if parsed.id is None or not parsed.name:
            raise ValueError("Use a valid custom emoji such as <:name:id>.")
        return str(parsed)
    if len(value) > 16 or any(character.isspace() for character in value):
        raise ValueError("Use one Unicode emoji or a custom emoji such as <:name:id>.")
    return value


def _emoji_matches(stored: str, payload_emoji: discord.PartialEmoji) -> bool:
    """Compare a stored mapping with a raw reaction payload."""
    if stored.startswith("<:") or stored.startswith("<a:"):
        parsed = discord.PartialEmoji.from_str(stored)
        return parsed.id == payload_emoji.id
    return str(payload_emoji) == stored


class ReactionRolePanelView(discord.ui.LayoutView):
    """Persistent Components V2 view for button and select panels."""

    def __init__(self, cog: "ReactionRolesCog", panel: Any, guild: discord.Guild) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.panel = panel
        self.guild = guild
        lines: list[discord.ui.Item[discord.ui.LayoutView]] = [
            discord.ui.TextDisplay(f"{E.bx_check}  **Reaction Roles**"),
            discord.ui.Separator(),
        ]
        mappings = [mapping for mapping in getattr(panel, "roles", []) if mapping.enabled]
        if mappings:
            lines.append(discord.ui.TextDisplay("\n".join(
                f"{mapping.emoji}  <@&{mapping.roleId}>" for mapping in mappings
            )))
        else:
            lines.append(discord.ui.TextDisplay("No role mappings have been added yet."))
        lines.append(discord.ui.Separator())
        lines.append(discord.ui.TextDisplay(f"{E.bx_arrow}  Choose an option to toggle your role."))

        if panel.mode == "buttons":
            buttons = []
            for mapping in mappings[:25]:
                role = guild.get_role(int(mapping.roleId))
                label = (mapping.label or (role.name if role else "Role"))[:80]
                button = discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=label,
                    emoji=_emoji_object(mapping.emoji),
                    custom_id=f"bypassx:rr:{panel.id}:{mapping.roleId}",
                )
                button.callback = self._button_callback
                buttons.append(button)
            for index in range(0, len(buttons), 5):
                lines.append(discord.ui.ActionRow(*buttons[index:index + 5]))
        elif panel.mode == "select" and mappings:
            options = []
            for mapping in mappings[:25]:
                role = guild.get_role(int(mapping.roleId))
                options.append(discord.SelectOption(
                    label=(mapping.label or (role.name if role else "Role"))[:100],
                    value=str(mapping.roleId),
                    emoji=_emoji_object(mapping.emoji),
                ))
            select = discord.ui.Select(
                custom_id=f"bypassx:rr-select:{panel.id}",
                placeholder="Choose a role",
                min_values=1,
                max_values=1,
                options=options,
            )
            select.callback = self._select_callback
            lines.append(discord.ui.ActionRow(select))

        self.add_item(discord.ui.Container(*lines, accent_color=0xE62334))

    async def _button_callback(self, interaction: discord.Interaction) -> None:
        custom_id = str(getattr(interaction.data, "get", lambda *_: "")("custom_id", ""))
        role_id = custom_id.rsplit(":", 1)[-1]
        await self.cog.toggle_member_role(interaction, self.panel, role_id)

    async def _select_callback(self, interaction: discord.Interaction) -> None:
        values = (interaction.data or {}).get("values", [])
        if not values:
            await interaction.response.send_message(**error("Choose a role first."), ephemeral=True)
            return
        await self.cog.toggle_member_role(interaction, self.panel, str(values[0]))


class ReactionRolesCog(commands.Cog):
    """Configure persistent reaction-role panels for this server."""

    reactionrole = app_commands.Group(name="reactionrole", description="Configure self-assignable roles.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    async def cog_load(self) -> None:
        """Restore enabled button and select panels after a restart."""
        try:
            panels = await self.db.reactionrolepanel.find_many(
                where={"enabled": True, "messageId": {"not": None}},
                include={"roles": True},
            )
        except Exception:
            logger.exception("Could not restore reaction-role panels")
            return
        for panel in panels:
            guild = self.bot.get_guild(int(panel.guildId))
            if guild is None or panel.mode == "reactions":
                continue
            try:
                self.bot.add_view(
                    ReactionRolePanelView(self, panel, guild),
                    message_id=int(panel.messageId),
                )
            except (TypeError, ValueError):
                logger.warning("Could not restore reaction-role panel %s", panel.id)

    async def _deploy(self, guild: discord.Guild, panel: Any, channel: discord.TextChannel) -> discord.Message:
        view = ReactionRolePanelView(self, panel, guild)
        if panel.messageId:
            try:
                message = await channel.fetch_message(int(panel.messageId))
                await message.edit(view=view)
                if panel.mode == "reactions":
                    for mapping in getattr(panel, "roles", []):
                        if mapping.enabled:
                            try:
                                await message.add_reaction(_emoji_object(mapping.emoji))
                            except discord.HTTPException:
                                logger.warning("Could not add reaction %s to panel %s", mapping.emoji, panel.id)
                return message
            except (discord.NotFound, discord.HTTPException):
                pass
        message = await channel.send(view=view)
        await set_panel_message(self.db, panel.id, str(message.id))
        if panel.mode == "reactions":
            for mapping in getattr(panel, "roles", []):
                if mapping.enabled:
                    try:
                        await message.add_reaction(_emoji_object(mapping.emoji))
                    except discord.HTTPException:
                        logger.warning("Could not add reaction %s to panel %s", mapping.emoji, panel.id)
        return message

    async def toggle_member_role(self, interaction: discord.Interaction, panel: Any, role_id: str) -> None:
        """Toggle one persisted mapping for the interacting guild member."""
        if interaction.guild is None or interaction.guild.id != int(panel.guildId):
            await interaction.response.send_message(**error("This panel belongs to another server."), ephemeral=True)
            return
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        role = interaction.guild.get_role(int(role_id))
        if member is None or role is None:
            await interaction.response.send_message(**error("The configured role is unavailable."), ephemeral=True)
            return
        bot_member = interaction.guild.me
        if role.managed or (bot_member is not None and role >= bot_member.top_role):
            await interaction.response.send_message(**error("The bot cannot manage this role. Move it below the bot's highest role."), ephemeral=True)
            return
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Reaction role removed")
                message = f"Removed {role.mention}."
            else:
                await member.add_roles(role, reason="Reaction role assigned")
                message = f"Added {role.mention}."
        except discord.Forbidden:
            await interaction.response.send_message(**error("Discord denied this role change."), ephemeral=True)
            return
        await interaction.response.send_message(**success(message), ephemeral=True)

    @reactionrole.command(name="setup", description="Create and deploy a reaction-role panel.")
    @app_commands.describe(channel="Channel where the panel should be deployed.", mode="Interaction mode for the panel.")
    @app_commands.choices(mode=_MODE_CHOICES)
    @require_tier(2)
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel, mode: app_commands.Choice[str]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        try:
            panel = await create_panel(self.db, str(interaction.guild.id), str(channel.id), mode.value)
            await self._deploy(interaction.guild, panel, channel)
        except discord.Forbidden:
            await interaction.response.send_message(**error("The bot cannot deploy a panel in that channel."), ephemeral=True)
            return
        await interaction.response.send_message(**success(f"Reaction-role panel `{panel.id}` deployed in {channel.mention}. Add mappings with `/reactionrole add`."), ephemeral=True)

    @reactionrole.command(name="add", description="Add or update an emoji-to-role mapping.")
    @app_commands.describe(panel="Panel ID.", emoji="Unicode or custom emoji, for example <:name:id>.", role="Role to assign.", label="Optional button or select label.")
    @require_tier(2)
    async def add(self, interaction: discord.Interaction, panel: str, emoji: str, role: discord.Role, label: str | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        record = await get_panel(self.db, panel)
        if record is None or str(record.guildId) != str(interaction.guild.id) or not record.enabled:
            await interaction.response.send_message(**error("That panel was not found in this server."), ephemeral=True)
            return
        mappings = await list_mappings(self.db, panel)
        try:
            normalized = _normalize_emoji(emoji)
        except ValueError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        if not any(str(item.emoji) == normalized for item in mappings) and len(mappings) >= 25:
            await interaction.response.send_message(**error("A Discord panel supports at most 25 role mappings."), ephemeral=True)
            return
        bot_member = interaction.guild.me
        if role.managed or (bot_member is not None and role >= bot_member.top_role):
            await interaction.response.send_message(**error("Move the selected role below the bot's highest role."), ephemeral=True)
            return
        await upsert_mapping(self.db, guild_id=str(interaction.guild.id), panel_id=panel, emoji=normalized, role_id=str(role.id), label=label)
        await interaction.response.send_message(**success(f"Mapping saved: {normalized} → {role.mention}. Redeploy the panel to refresh its controls."), ephemeral=True)

    @reactionrole.command(name="remove", description="Remove an emoji-to-role mapping.")
    @app_commands.describe(panel="Panel ID.", emoji="The emoji mapping to remove.")
    @require_tier(2)
    async def remove(self, interaction: discord.Interaction, panel: str, emoji: str) -> None:
        try:
            normalized = _normalize_emoji(emoji)
        except ValueError as exc:
            await interaction.response.send_message(**error(str(exc)), ephemeral=True)
            return
        record = await get_panel(self.db, panel)
        if record is None or interaction.guild is None or str(record.guildId) != str(interaction.guild.id):
            await interaction.response.send_message(**error("That panel was not found in this server."), ephemeral=True)
            return
        await delete_mapping(self.db, panel, normalized)
        await interaction.response.send_message(**success(f"Removed the `{normalized}` role mapping. Redeploy the panel to refresh it."), ephemeral=True)

    @reactionrole.command(name="deploy", description="Refresh an existing panel after changing mappings.")
    @app_commands.describe(panel="Panel ID.")
    @require_tier(2)
    async def deploy(self, interaction: discord.Interaction, panel: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        record = await get_panel(self.db, panel)
        if record is None or str(record.guildId) != str(interaction.guild.id) or not record.enabled:
            await interaction.response.send_message(**error("That panel was not found in this server."), ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(record.channelId))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(**error("The configured panel channel is unavailable."), ephemeral=True)
            return
        record.roles = await list_mappings(self.db, panel)
        await self._deploy(interaction.guild, record, channel)
        await interaction.response.send_message(**success(f"Reaction-role panel `{panel}` refreshed."), ephemeral=True)

    @reactionrole.command(name="list", description="List reaction-role panels and mappings.")
    @require_tier(2)
    async def list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        panels = await list_panels(self.db, str(interaction.guild.id))
        if not panels:
            await interaction.response.send_message(**information("Reaction Roles", "No panels are configured."), ephemeral=True)
            return
        rows = []
        for panel in panels:
            mappings = getattr(panel, "roles", [])
            rows.append(f"`{panel.id}` · `{panel.mode}` · {len(mappings)} mapping(s) · {'enabled' if panel.enabled else 'disabled'}")
        await interaction.response.send_message(**information("Reaction Roles", "\n".join(rows)), ephemeral=True)

    @reactionrole.command(name="disable", description="Disable a reaction-role panel without deleting its mappings.")
    @app_commands.describe(panel="Panel ID.")
    @require_tier(2)
    async def disable(self, interaction: discord.Interaction, panel: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        record = await get_panel(self.db, panel)
        if record is None or str(record.guildId) != str(interaction.guild.id):
            await interaction.response.send_message(**error("That panel was not found in this server."), ephemeral=True)
            return
        await disable_panel(self.db, panel)
        await interaction.response.send_message(**success(f"Reaction-role panel `{panel}` disabled."), ephemeral=True)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, *, adding: bool) -> None:
        if payload.guild_id is None or (self.bot.user and payload.user_id == self.bot.user.id):
            return
        panel = await get_panel_for_message(self.db, str(payload.guild_id), str(payload.message_id))
        if panel is None or panel.mode != "reactions":
            return
        mapping = next((item for item in getattr(panel, "roles", []) if item.enabled and _emoji_matches(item.emoji, payload.emoji)), None)
        if mapping is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return
        role = guild.get_role(int(mapping.roleId))
        if role is None or role.managed:
            return
        try:
            if adding:
                await member.add_roles(role, reason="Reaction role assigned")
            else:
                await member.remove_roles(role, reason="Reaction role removed")
        except discord.HTTPException:
            return

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_reaction(payload, adding=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_reaction(payload, adding=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReactionRolesCog(bot))
