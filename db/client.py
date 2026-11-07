"""Prisma client lifecycle for BypassX.

The client is deliberately kept behind a small wrapper so the Bot class does
not need to know Prisma implementation details and future health checks can be
added in one place.
"""

from __future__ import annotations

import logging
import asyncio

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

    async def connect(self, *, retries: int = 5, base_delay: float = 2.0) -> None:
        """Open the database connection, failing startup if it is unavailable."""
        if self._connected:
            return

        logger.info("Connecting to PostgreSQL through Prisma")
        last_error: Exception | None = None
        for attempt in range(1, max(1, retries) + 1):
            try:
                await self.client.connect()
                await self.client.query_raw("SELECT 1")
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning("PostgreSQL connection attempt %d/%d failed; retrying in %.1fs", attempt, retries, delay)
                try:
                    await self.client.disconnect()
                except Exception:
                    logger.debug("Prisma disconnect after failed connection was unsuccessful", exc_info=True)
                await asyncio.sleep(delay)
            else:
                self._connected = True
                logger.info("PostgreSQL connection established and health check passed")
                return
        raise RuntimeError("Could not connect to PostgreSQL after retries") from last_error

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
