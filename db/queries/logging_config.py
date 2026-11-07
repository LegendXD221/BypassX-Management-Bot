"""Persistent logging configuration queries."""

from __future__ import annotations

from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


LOG_FIELDS: dict[str, str] = {
    "message_delete": "messageDelete",
    "message_edit": "messageEdit",
    "member_join": "memberJoin",
    "member_leave": "memberLeave",
    "ban_kick": "banKick",
    "role_change": "roleChange",
    "channel_change": "channelChange",
    "voice_activity": "voiceActivity",
    "invite_activity": "inviteActivity",
    "member_update": "memberUpdate",
    "mod_actions": "modActions",
}


async def get_log_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch one guild's logging configuration."""
    return await db.logconfig.find_unique(where={"guildId": guild_id})


async def set_log_channel(db: Prisma, guild_id: str, event: str, channel_id: str) -> Any:
    """Assign a channel to one supported event category."""
    field = LOG_FIELDS.get(event)
    if field is None:
        raise ValueError(f"Unsupported logging event: {event}")
    await ensure_guild(db, guild_id)
    return await db.logconfig.upsert(
        where={"guildId": guild_id},
        data={
            "create": {"guildId": guild_id, field: channel_id},
            "update": {field: channel_id},
        },
    )


async def disable_log_event(db: Prisma, guild_id: str, event: str) -> Any | None:
    """Disable one logging event category without affecting other categories."""
    field = LOG_FIELDS.get(event)
    if field is None:
        raise ValueError(f"Unsupported logging event: {event}")
    config = await get_log_config(db, guild_id)
    if config is None:
        return None
    return await db.logconfig.update(
        where={"guildId": guild_id},
        data={field: None},
    )


async def reset_log_config(db: Prisma, guild_id: str) -> int:
    """Delete all logging assignments for a guild."""
    result = await db.logconfig.delete_many(where={"guildId": guild_id})
    return result if isinstance(result, int) else result.count


__all__ = ["LOG_FIELDS", "disable_log_event", "get_log_config", "reset_log_config", "set_log_channel"]
