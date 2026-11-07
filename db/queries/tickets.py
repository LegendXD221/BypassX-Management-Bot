"""Support ticket configuration and lifecycle queries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from prisma import Prisma

from db.queries.guild import ensure_guild


async def get_ticket_config(db: Prisma, guild_id: str) -> Any | None:
    """Fetch the ticket configuration for a guild."""
    return await db.ticketconfig.find_unique(where={"guildId": guild_id})


async def upsert_ticket_config(db: Prisma, guild_id: str, **changes: Any) -> Any:
    """Create or update supported ticket configuration values."""
    allowed = {"categoryId", "logChannel", "supportRole", "panelMsg", "maxPerUser"}
    data = {key: value for key, value in changes.items() if key in allowed}
    await ensure_guild(db, guild_id)
    return await db.ticketconfig.upsert(
        where={"guildId": guild_id},
        data={"create": {"guildId": guild_id, **data}, "update": data},
    )


async def create_ticket(db: Prisma, guild_id: str, channel_id: str, owner_id: str) -> Any:
    """Create an open ticket record for a Discord channel."""
    return await db.ticket.create(
        data={"guildId": guild_id, "channelId": channel_id, "ownerId": owner_id}
    )


async def get_ticket(db: Prisma, ticket_id: str) -> Any | None:
    """Fetch a ticket by its CUID."""
    return await db.ticket.find_unique(where={"id": ticket_id})


async def get_ticket_by_channel(db: Prisma, channel_id: str) -> Any | None:
    """Fetch the open ticket associated with a Discord channel."""
    return await db.ticket.find_first(
        where={"channelId": channel_id, "status": "open"},
        order={"createdAt": "desc"},
    )


async def get_open_ticket_for_user(db: Prisma, guild_id: str, owner_id: str) -> Any | None:
    """Find a user's currently open ticket in a guild."""
    return await db.ticket.find_first(
        where={"guildId": guild_id, "ownerId": owner_id, "status": "open"},
        order={"createdAt": "asc"},
    )


async def count_open_tickets(db: Prisma, guild_id: str, owner_id: str) -> int:
    """Count a user's open tickets in a guild."""
    return await db.ticket.count(where={"guildId": guild_id, "ownerId": owner_id, "status": "open"})


async def list_open_tickets(db: Prisma, guild_id: str) -> list[Any]:
    """Return all open tickets in a guild, oldest first."""
    return await db.ticket.find_many(where={"guildId": guild_id, "status": "open"}, order={"createdAt": "asc"})


async def claim_ticket(db: Prisma, ticket_id: str, staff_id: str) -> Any:
    """Assign an open ticket to a staff member."""
    return await db.ticket.update(where={"id": ticket_id}, data={"claimedBy": staff_id})


async def unclaim_ticket(db: Prisma, ticket_id: str) -> Any:
    """Release the current ticket claim."""
    return await db.ticket.update(where={"id": ticket_id}, data={"claimedBy": None})


async def set_ticket_control_message(db: Prisma, ticket_id: str, message_id: str) -> Any:
    """Persist the message containing the ticket's control buttons."""
    return await db.ticket.update(
        where={"id": ticket_id},
        data={"controlMessageId": message_id},
    )


async def close_ticket(db: Prisma, ticket_id: str, closed_at: datetime | None = None) -> Any:
    """Mark a ticket closed and record its closing timestamp."""
    return await db.ticket.update(
        where={"id": ticket_id},
        data={"status": "closed", "closedAt": closed_at or datetime.now(timezone.utc)},
    )
