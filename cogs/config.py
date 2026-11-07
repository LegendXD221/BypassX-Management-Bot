"""Configuration Cog.

Category    : Configuration
Emoji       : bx_gear
Color       : #7F8C8D
Description : Server configuration controls.
"""

from __future__ import annotations

import io
import json
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from ui.containers import error, information, success, warning
from ui.modals import confirmation_modal
from db.queries.guild import (
    ensure_guild,
    get_guild,
    list_mod_tiers,
    remove_mod_tier,
    reset_guild,
    update_guild,
    upsert_mod_tier,
)


class ConfigCog(commands.Cog):
    """Manage per-guild BypassX settings."""

    config = app_commands.Group(name="config", description="Manage BypassX server configuration.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

    @staticmethod
    def _guild(interaction: discord.Interaction) -> discord.Guild | None:
        return interaction.guild

    @config.command(name="prefix", description="Set the bot prefix for this server.")
    @app_commands.describe(prefix="The new prefix, from 1 to 5 characters.")
    @require_tier(2)
    async def prefix(self, interaction: discord.Interaction, prefix: str) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        prefix = prefix.strip()
        if not 1 <= len(prefix) <= 5 or prefix.isspace():
            await interaction.response.send_message(**error("Prefix must contain 1–5 non-space characters."), ephemeral=True)
            return
        await update_guild(self.db, str(guild.id), prefix=prefix)
        await interaction.response.send_message(**success(f"Prefix set to `{prefix}`."), ephemeral=True)

    @config.command(name="language", description="Set the bot language for this server.")
    @app_commands.describe(language="Language code, for example en.")
    @require_tier(2)
    async def language(self, interaction: discord.Interaction, language: str) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        language = language.strip().lower()
        if not 2 <= len(language) <= 8 or not language.isalpha():
            await interaction.response.send_message(**error("Language must be an alphabetic language code."), ephemeral=True)
            return
        await update_guild(self.db, str(guild.id), language=language)
        await interaction.response.send_message(**success(f"Language set to `{language}`."), ephemeral=True)

    @config.command(name="modtier", description="Assign a staff role to a permission tier.")
    @app_commands.describe(role="The staff role.", tier="0=everyone, 1=moderator, 2=admin, 3=owner.")
    @require_tier(2)
    async def modtier(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        tier: app_commands.Range[int, 0, 3],
    ) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_mod_tier(self.db, str(guild.id), str(role.id), int(tier))
        await interaction.response.send_message(
            **success(f"{role.mention} assigned to permission tier `{tier}`."),
            ephemeral=True,
        )

    @config.command(name="view", description="View the full server configuration.")
    @require_tier(2)
    async def view(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        record = await get_guild(self.db, str(guild.id)) or await ensure_guild(self.db, str(guild.id))
        tiers = await list_mod_tiers(self.db, str(guild.id))
        tier_rows = "\n".join(f"• <@&{row.roleId}> → tier {row.tier}" for row in tiers) or "None configured"
        message = (
            f"**Prefix**  `{record.prefix}`\n"
            f"**Language**  `{record.language}`\n"
            f"**Staff tiers**\n{tier_rows}"
        )
        await interaction.response.send_message(
            **information("Server Configuration", message, accent=0xFFFFFF),
            ephemeral=True,
        )

    async def _reset_guild(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await reset_guild(self.db, str(guild.id))
        await interaction.response.send_message(**success("Server configuration reset."), ephemeral=True)

    @config.command(name="reset", description="Reset the full server configuration.")
    @require_tier(3)
    async def reset(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            confirmation_modal("RESET", lambda interaction, _values: self._reset_guild(interaction))
        )

    @config.command(name="export", description="Export server configuration as JSON.")
    @require_tier(2)
    async def export(self, interaction: discord.Interaction) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        record = await get_guild(self.db, str(guild.id)) or await ensure_guild(self.db, str(guild.id))
        tiers = await list_mod_tiers(self.db, str(guild.id))
        payload = {
            "guild_id": str(guild.id),
            "prefix": record.prefix,
            "language": record.language,
            "mod_tiers": [{"role_id": row.roleId, "tier": row.tier} for row in tiers],
        }
        file = discord.File(
            io.BytesIO(json.dumps(payload, indent=2).encode("utf-8")),
            filename=f"bypassx-config-{guild.id}.json",
        )
        await interaction.response.send_message(
            **information("Configuration Export", "The server configuration is attached as JSON."),
            file=file,
            ephemeral=True,
        )

    @config.command(name="import", description="Import server configuration from JSON.")
    @app_commands.describe(payload="JSON object containing prefix, language, and optional mod_tiers.")
    @require_tier(2)
    async def import_config(self, interaction: discord.Interaction, payload: str) -> None:
        guild = self._guild(interaction)
        if guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            await interaction.response.send_message(**error("Payload is not valid JSON."), ephemeral=True)
            return
        if not isinstance(data, dict):
            await interaction.response.send_message(**error("Configuration payload must be a JSON object."), ephemeral=True)
            return

        imported_tiers = data.get("mod_tiers", [])
        if not isinstance(imported_tiers, list):
            await interaction.response.send_message(**error("mod_tiers must be a JSON array."), ephemeral=True)
            return

        changes: dict[str, str] = {}
        if "prefix" in data:
            prefix = str(data["prefix"]).strip()
            if not 1 <= len(prefix) <= 5:
                await interaction.response.send_message(**error("Imported prefix must contain 1–5 characters."), ephemeral=True)
                return
            changes["prefix"] = prefix
        if "language" in data:
            language = str(data["language"]).strip().lower()
            if not language.isalpha() or not 2 <= len(language) <= 8:
                await interaction.response.send_message(**error("Imported language is invalid."), ephemeral=True)
                return
            changes["language"] = language
        await update_guild(self.db, str(guild.id), **changes)

        existing_tiers = await list_mod_tiers(self.db, str(guild.id))
        imported_role_ids = {
            str(item.get("role_id"))
            for item in imported_tiers
            if isinstance(item, dict) and str(item.get("role_id", "")).isdigit()
        }
        for existing in existing_tiers:
            if str(existing.roleId) not in imported_role_ids:
                await remove_mod_tier(self.db, str(guild.id), str(existing.roleId))
        for item in imported_tiers:
            if not isinstance(item, dict):
                continue
            role_id = str(item.get("role_id", ""))
            tier = item.get("tier")
            if role_id.isdigit() and isinstance(tier, int) and 0 <= tier <= 3:
                await upsert_mod_tier(self.db, str(guild.id), role_id, tier)

        await interaction.response.send_message(**success("Server configuration imported."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigCog(bot))
