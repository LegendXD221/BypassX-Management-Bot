"""BypassX Management entry point."""

from __future__ import annotations

import asyncio
import logging

from config.settings import settings
from core.bot import BypassX


logger = logging.getLogger(__name__)


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
    try:
        await bot.start(settings.bot_token)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by operator")
    except Exception:
        logger.exception("Fatal bot runtime failure")
        raise
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger(__name__).exception("BypassX exited unsuccessfully: %s", exc)
        raise SystemExit(1) from exc
