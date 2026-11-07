"""Dynamic Components V2 help menu.

The menu inspects loaded Cogs at runtime. Adding a Cog with metadata and
commands automatically adds it to the dropdown without editing this module.
"""

from __future__ import annotations

import inspect
import re
import sys
from dataclasses import dataclass
from typing import Any

import discord
from discord.ext import commands

from config.colors import CONFIGURATION, NEUTRAL
from config.emojis import E


_METADATA_PATTERN = re.compile(r"^\s*(Category|Emoji|Color|Description)\s*:\s*(.+?)\s*$", re.I | re.M)


@dataclass(frozen=True, slots=True)
class CogHelp:
    """Help metadata and commands for one loaded Cog."""

    key: str
    category: str
    emoji: str
    color: int
    description: str
    commands: tuple[tuple[str, str], ...]


CATEGORY_DEFAULTS: dict[str, tuple[str, str, int, str]] = {
    "moderation": ("Moderation", "bx_shield", 0xE62334, "Server moderation controls."),
    "logging": ("Logging", "bx_log", 0xE62334, "Audit and event logging controls."),
    "automod": ("AutoMod", "bx_bolt", 0xE62334, "Automated protection controls."),
    "verification": ("Verification", "bx_check", 0xFFFFFF, "Member verification controls."),
    "leveling": ("Leveling", "bx_crown", 0xE62334, "Experience and rank controls."),
    "economy": ("Economy", "bx_coin", 0xE62334, "Economy and shop controls."),
    "tickets": ("Tickets", "bx_ticket", 0xE62334, "Support ticket controls."),
    "welcome": ("Welcome", "bx_wave", 0xFFFFFF, "Welcome and farewell controls."),
    "stats": ("Server Stats", "bx_pulse", 0xE62334, "Server statistics controls."),
    "giveaways": ("Giveaways", "bx_gift", 0xE62334, "Giveaway controls."),
    "reminders": ("Reminders", "bx_bell", 0xFFFFFF, "Reminder controls."),
    "utility": ("Utility", "bx_star", 0xE62334, "General utility commands."),
    "config": ("Configuration", "bx_gear", CONFIGURATION, "Server configuration controls."),
}


def _parse_metadata(cog: commands.Cog) -> dict[str, str]:
    module = sys.modules.get(cog.__module__)
    source = "\n".join(
        value
        for value in (
            inspect.getdoc(cog.__class__),
            inspect.getdoc(module) if module else None,
        )
        if value
    )
    return {key.lower(): value.strip() for key, value in _METADATA_PATTERN.findall(source)}


def _parse_color(value: str | None, fallback: int) -> int:
    if not value:
        return fallback
    try:
        return int(value.strip().lstrip("#"), 16)
    except ValueError:
        return fallback


def _command_rows(cog: commands.Cog) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for command in cog.get_app_commands():
        description = getattr(command, "description", "No description provided.")
        rows.append((f"/{command.qualified_name}", description))

    for command in cog.walk_commands():
        if any(name == f"/{command.qualified_name}" for name, _ in rows):
            continue
        rows.append((f"?{command.qualified_name}", command.help or "No description provided."))
    return tuple(rows)


def discover_help(bot: commands.Bot) -> tuple[CogHelp, ...]:
    """Build sorted help metadata from every currently loaded Cog."""
    discovered: list[CogHelp] = []
    for key, cog in bot.cogs.items():
        module_key = cog.__module__.rsplit(".", 1)[-1].lower()
        fallback = CATEGORY_DEFAULTS.get(
            module_key,
            (key, "bx_star", NEUTRAL, "Feature commands."),
        )
        metadata = _parse_metadata(cog)
        category = metadata.get("category", fallback[0])
        emoji_key = metadata.get("emoji", fallback[1]).replace("E.", "")
        emoji = getattr(E, emoji_key, E.bx_star)
        color = _parse_color(metadata.get("color"), fallback[2])
        description = metadata.get("description", fallback[3])
        discovered.append(
            CogHelp(
                key=module_key,
                category=category,
                emoji=emoji,
                color=color,
                description=description,
                commands=_command_rows(cog),
            )
        )
    return tuple(sorted(discovered, key=lambda item: item.category.casefold()))


def _select_options(categories: tuple[CogHelp, ...], selected: str | None) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=item.category[:100],
            value=item.key,
            description=item.description[:100],
            emoji=item.emoji,
            default=item.key == selected,
        )
        for item in categories
    ]


class HelpSelect(discord.ui.Select):
    """Dropdown that edits the current ephemeral help message in place."""

    def __init__(self, bot: commands.Bot, categories: tuple[CogHelp, ...], selected: str | None) -> None:
        self.bot = bot
        self.categories = categories
        super().__init__(
            placeholder="Browse Categories",
            custom_id="help_category_select",
            min_values=1,
            max_values=1,
            options=_select_options(categories, selected),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        await interaction.response.edit_message(view=build_help_view(self.bot, selected))


def _help_container(bot: commands.Bot, selected: str | None) -> discord.ui.Container:
    categories = discover_help(bot)
    select = HelpSelect(bot, categories, selected)
    action_row = discord.ui.ActionRow(select)

    if selected is None:
        return discord.ui.Container(
            discord.ui.TextDisplay(
                f"{E.bx_shield}  **BypassX · Management Suite**\n"
                "────────────────────────────────────────\n"
                "Select a category below to view commands."
            ),
            discord.ui.Separator(),
            action_row,
            accent_color=0xE62334,
        )

    category = next((item for item in categories if item.key == selected), None)
    if category is None:
        return _help_container(bot, None)

    rows = "\n".join(
        f"`{name}`  ·  {description}" for name, description in category.commands
    ) or "No commands registered yet."
    return discord.ui.Container(
        discord.ui.TextDisplay(f"{category.emoji}  **{category.category}**"),
        discord.ui.TextDisplay(category.description),
        discord.ui.Separator(),
        discord.ui.TextDisplay(rows),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"{E.bx_arrow}  Read-only  ·  Use / to run commands"),
        action_row,
        accent_color=category.color,
    )


def build_help_view(bot: commands.Bot, selected: str | None = None) -> discord.ui.LayoutView:
    """Build the complete help view for the entry screen or a category."""
    view = discord.ui.LayoutView(timeout=300)
    view.add_item(_help_container(bot, selected))
    return view


async def send_help(interaction: discord.Interaction, bot: commands.Bot) -> None:
    """Send the initial ephemeral help menu."""
    await interaction.response.send_message(view=build_help_view(bot), ephemeral=True)


__all__ = ["CogHelp", "build_help_view", "discover_help", "send_help"]
