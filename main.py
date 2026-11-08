"""BypassX Management entry point."""

from __future__ import annotations

import asyncio
import logging
import os

import discord

from config.settings import settings
from core.bot import BypassX


logger = logging.getLogger(__name__)


async def _health_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Serve Render's health check without adding a web framework dependency."""
    try:
        await reader.read(1024)
        body = b'{"status":"ok","service":"bypassx-management"}'
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        writer.write(response)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def start_health_server() -> asyncio.AbstractServer:
    """Bind the Render-provided port for Web Service health checks."""
    port = int(os.getenv("PORT", "10000"))
    return await asyncio.start_server(_health_handler, host="0.0.0.0", port=port)


def configure_logging() -> None:
    """Configure consistent stdout logging for local and Render deployments."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


async def main() -> None:
    """Create and run the bot until Discord or the process requests shutdown."""
    configure_logging()
    settings.validate()

    bot = BypassX()
    health_server = await start_health_server()
    try:
        rate_limit_retries = 0
        while True:
            try:
                await bot.start(settings.bot_token)
                break
            except discord.HTTPException as exc:
                status = getattr(exc.response, "status", None)
                if status != 429 or rate_limit_retries >= 5:
                    raise
                rate_limit_retries += 1
                delay = min(300, 60 * rate_limit_retries)
                logger.warning(
                    "Discord gateway rate limited the bot; retrying in %s seconds (attempt %s/5)",
                    delay,
                    rate_limit_retries,
                )
                await bot.close()
                await asyncio.sleep(delay)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by operator")
    except Exception:
        logger.exception("Fatal bot runtime failure")
        raise
    finally:
        health_server.close()
        await health_server.wait_closed()
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger(__name__).exception("BypassX exited unsuccessfully: %s", exc)
        raise SystemExit(1) from exc
