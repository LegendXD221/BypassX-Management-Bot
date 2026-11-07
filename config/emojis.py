"""Central BypassX application-emoji registry.

The registry starts with Unicode fallbacks so the bot remains usable before the
application emoji API is available. ``sync_application_emojis`` replaces these
values with Discord application-emoji markup after startup.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class EmojiSet:
    bx_shield: str = "◆"
    bx_log: str = "▤"
    bx_tick: str = "✓"
    bx_cross: str = "×"
    bx_warn: str = "!"
    bx_lock: str = "■"
    bx_star: str = "★"
    bx_user: str = "●"
    bx_gear: str = "⚙"
    bx_pulse: str = "≋"
    bx_ticket: str = "▣"
    bx_crown: str = "♛"
    bx_coin: str = "$"
    bx_gift: str = "✦"
    bx_arrow: str = "➜"
    bx_bolt: str = "ϟ"
    bx_check: str = "✓"
    bx_bell: str = "♢"
    bx_wave: str = "⌁"
    bx_chart: str = "▥"

    def set_markup(self, name: str, markup: str) -> None:
        """Replace one registry entry after an application emoji is loaded."""
        if not hasattr(self, name):
            raise AttributeError(name)
        setattr(self, name, markup)


E = EmojiSet()
EMOJI_NAMES = tuple(name for name in EmojiSet.__annotations__)
