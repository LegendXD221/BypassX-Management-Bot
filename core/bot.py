"""Core BypassX Bot class and startup lifecycle."""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from config.settings import settings
from core.application_emojis import sync_application_emojis
from db.client import Database
from core.errors import handle_app_command_error, handle_prefix_error


logger = logging.getLogger(__name__)


class BypassX(commands.Bot):
    """Application bot with database-backed startup and dynamic Cogs."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix=self._prefix,
            intents=intents,
            help_command=None,
        )
        self.database = Database()
        # Compatibility alias for Cogs that use the specification's self.db API.
        self.db = self.database.client
        self._shutdown_complete = False
        self._application_emojis_synced = False
        self.tree.on_error = self.on_app_command_error

    async def _prefix(self, _bot: commands.Bot, _message: discord.Message) -> str:
        """Return the configured guild prefix, falling back safely to ``?``."""
        guild = _message.guild
        if guild is None or not self.database.connected:
            return "?"
        try:
            record = await self.db.guild.find_unique(where={"id": str(guild.id)})
            return record.prefix if record and record.prefix else "?"
        except Exception:
            logger.exception("Could not load prefix for guild %s", guild.id)
            return "?"

    async def setup_hook(self) -> None:
        """Connect dependencies, load Cogs, and synchronize application commands."""
        settings.validate()
        logger.info("Starting BypassX in %s environment", settings.environment)

        await self.database.connect()
        await self.load_cogs()
        await self.sync_commands()

    async def load_cogs(self) -> tuple[str, ...]:
        """Discover and load every Python Cog module under the project Cogs path."""
        cog_path = Path(__file__).resolve().parent.parent / "cogs"
        loaded: list[str] = []

        for file in sorted(cog_path.glob("*.py")):
            if file.name.startswith("_"):
                continue

            extension = f"cogs.{file.stem}"
            try:
                await self.load_extension(extension)
            except commands.ExtensionAlreadyLoaded:
                logger.debug("Cog already loaded: %s", extension)
            except Exception:
                logger.exception("Failed to load Cog: %s", extension)
            else:
                loaded.append(extension)
                logger.info("Loaded Cog: %s", extension)

        logger.info("Dynamic Cog loading complete: %d loaded", len(loaded))
        return tuple(loaded)

    async def sync_commands(self) -> int:
        """Sync slash commands globally or to configured development guilds."""
        if settings.dev_guild_ids:
            synced = 0
            for guild_id in settings.dev_guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                commands_for_guild = await self.tree.sync(guild=guild)
                synced += len(commands_for_guild)
                logger.info(
                    "Synchronized %d application commands to development guild %s",
                    len(commands_for_guild),
                    guild_id,
                )
            return synced

        commands_synced = await self.tree.sync()
        logger.info(
            "Synchronized %d application commands globally", len(commands_synced)
        )
        return len(commands_synced)

    async def on_ready(self) -> None:
        """Log gateway readiness; this event may fire more than once."""
        try:
            database_ok = await self.database.healthcheck()
        except Exception:
            database_ok = False
            logger.exception("Database health check failed after gateway readiness")
        if not database_ok:
            logger.error("Gateway is ready but the database health check is unavailable")
        if not self._application_emojis_synced:
            await sync_application_emojis(self)
            self._application_emojis_synced = True
        if self.user is not None:
            logger.info("Connected as %s (%s)", self.user, self.user.id)

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Route prefix-command failures through the shared handler."""
        await handle_prefix_error(ctx, error)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Route slash-command failures through the shared handler."""
        await handle_app_command_error(interaction, error)

    async def close(self) -> None:
        """Close Discord and Prisma resources exactly once."""
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        try:
            await super().close()
        except Exception:
            logger.exception("Discord shutdown encountered an error")
        finally:
            try:
                await self.database.disconnect()
            except Exception:
                logger.exception("Database shutdown encountered an error")
            logger.info("BypassX shutdown complete")
