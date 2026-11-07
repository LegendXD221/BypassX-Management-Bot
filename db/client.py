"""Prisma client lifecycle for BypassX.

The client is deliberately kept behind a small wrapper so the Bot class does
not need to know Prisma implementation details and future health checks can be
added in one place.
"""

from __future__ import annotations

import logging

from prisma import Prisma


logger = logging.getLogger(__name__)


class Database:
    """Own and manage one async Prisma client for the bot process."""

    def __init__(self) -> None:
        self.client = Prisma()
        self._connected = False

    @property
    def connected(self) -> bool:
        """Whether the underlying Prisma client is connected."""
        return self._connected

    async def connect(self) -> None:
        """Open the database connection, failing startup if it is unavailable."""
        if self._connected:
            return

        logger.info("Connecting to PostgreSQL through Prisma")
        await self.client.connect()
        self._connected = True
        logger.info("PostgreSQL connection established")

    async def disconnect(self) -> None:
        """Close the database connection during graceful shutdown."""
        if not self._connected:
            return

        logger.info("Closing PostgreSQL connection")
        await self.client.disconnect()
        self._connected = False
        logger.info("PostgreSQL connection closed")

    async def healthcheck(self) -> bool:
        """Run a lightweight query to verify database availability."""
        if not self._connected:
            return False

        await self.client.query_raw("SELECT 1")
        return True
