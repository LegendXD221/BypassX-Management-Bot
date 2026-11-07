"""Prisma persistence helpers for reaction-role panels."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild

REACTION_ROLE_MODES = ("reactions", "buttons", "select")


async def create_panel(db: Prisma, guild_id: str, channel_id: str, mode: str) -> Any:
    """Create a disabled-until-deployed reaction-role panel record."""
    if mode not in REACTION_ROLE_MODES:
        raise ValueError(f"Unsupported reaction-role mode: {mode}")
    await ensure_guild(db, guild_id)
    return await db.reactionrolepanel.create(
        data={
            "guildId": guild_id,
            "channelId": channel_id,
            "mode": mode,
            "enabled": True,
        }
    )


async def get_panel(db: Prisma, panel_id: str, *, include_roles: bool = True) -> Any | None:
    """Fetch one panel and its mappings."""
    return await db.reactionrolepanel.find_unique(
        where={"id": panel_id},
        include={"roles": include_roles},
    )


async def get_panel_for_message(db: Prisma, guild_id: str, message_id: str) -> Any | None:
    """Fetch an enabled panel by guild and Discord message ID."""
    return await db.reactionrolepanel.find_first(
        where={"guildId": guild_id, "messageId": message_id, "enabled": True},
        include={"roles": True},
    )


async def list_panels(db: Prisma, guild_id: str, *, enabled_only: bool = False) -> list[Any]:
    """List a guild's reaction-role panels with mappings."""
    where: dict[str, Any] = {"guildId": guild_id}
    if enabled_only:
        where["enabled"] = True
    return await db.reactionrolepanel.find_many(
        where=where,
        include={"roles": True},
        order={"createdAt": "desc"},
    )


async def set_panel_message(db: Prisma, panel_id: str, message_id: str) -> Any:
    """Persist the Discord message used by a deployed panel."""
    return await db.reactionrolepanel.update(
        where={"id": panel_id},
        data={"messageId": message_id, "enabled": True},
    )


async def disable_panel(db: Prisma, panel_id: str) -> Any:
    """Disable a panel without deleting its mappings."""
    return await db.reactionrolepanel.update(
        where={"id": panel_id},
        data={"enabled": False},
    )


async def upsert_mapping(
    db: Prisma,
    *,
    guild_id: str,
    panel_id: str,
    emoji: str,
    role_id: str,
    label: str | None = None,
) -> Any:
    """Create or update one emoji-to-role mapping on a panel."""
    return await db.reactionrole.upsert(
        where={"panelId_emoji": {"panelId": panel_id, "emoji": emoji}},
        data={
            "create": {
                "guildId": guild_id,
                "panelId": panel_id,
                "emoji": emoji,
                "roleId": role_id,
                "label": label,
                "enabled": True,
            },
            "update": {"roleId": role_id, "label": label, "enabled": True},
        },
    )


async def delete_mapping(db: Prisma, panel_id: str, emoji: str) -> None:
    """Delete one emoji-to-role mapping."""
    await db.reactionrole.delete(
        where={"panelId_emoji": {"panelId": panel_id, "emoji": emoji}}
    )


async def list_mappings(db: Prisma, panel_id: str) -> list[Any]:
    """List enabled mappings for one panel."""
    return await db.reactionrole.find_many(
        where={"panelId": panel_id, "enabled": True},
        order={"emoji": "asc"},
    )


__all__ = [
    "REACTION_ROLE_MODES",
    "create_panel",
    "delete_mapping",
    "disable_panel",
    "get_panel",
    "get_panel_for_message",
    "list_mappings",
    "list_panels",
    "set_panel_message",
    "upsert_mapping",
]
