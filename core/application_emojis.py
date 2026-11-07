"""Discord application-emoji synchronization for the BypassX theme."""

from __future__ import annotations

import logging
import base64
from pathlib import Path

import discord

from config.emojis import E, EMOJI_NAMES

logger = logging.getLogger(__name__)
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "emojis"


async def sync_application_emojis(bot: discord.Client) -> dict[str, str]:
    """Create missing application emojis and update the process-wide registry.

    Application emojis belong to the Discord application, not to any guild, so
    one successful synchronization makes them available to every guild where
    the application is installed.
    """
    try:
        existing = {emoji.name: emoji for emoji in await bot.fetch_application_emojis()}
    except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
        logger.warning("Application emoji synchronization unavailable: %s", exc)
        return {}

    synced: dict[str, str] = {}
    for name in EMOJI_NAMES:
        emoji = existing.get(name)
        asset = ASSET_DIR / f"{name}.png"
        image = asset.read_bytes() if asset.exists() else None
        if emoji is None:
            if image is None:
                logger.warning("Missing application emoji asset: %s", name)
                continue
            try:
                emoji = await bot.create_application_emoji(name=name, image=image)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
                logger.warning("Could not create application emoji %s: %s", name, exc)
                continue
        elif image is not None and getattr(bot, "application_id", None) is not None:
            # discord.py exposes creation publicly but not editing. Use the
            # documented HTTP route so a same-named old emoji gets the new art.
            try:
                encoded = base64.b64encode(image).decode("ascii")
                await bot.http.edit_application_emoji(
                    bot.application_id,
                    emoji.id,
                    payload={"name": name, "image": f"data:image/png;base64,{encoded}"},
                )
            except (AttributeError, discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
                logger.warning("Could not refresh application emoji %s: %s", name, exc)
        markup = str(emoji)
        E.set_markup(name, markup)
        synced[name] = markup

    logger.info("Application emoji synchronization complete: %d/%d available", len(synced), len(EMOJI_NAMES))
    return synced
