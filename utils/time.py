"""Duration parsing and humanization helpers."""

from __future__ import annotations

import re


_DURATION_PATTERN = re.compile(r"(?P<value>\d+)\s*(?P<unit>w|d|h|m|s)", re.I)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


class DurationParseError(ValueError):
    """Raised when a duration string is invalid or empty."""


def parse_duration(value: str, *, maximum: int | None = None) -> int:
    """Parse strings such as ``2h 30m`` into whole seconds."""
    text = value.strip().lower()
    if not text:
        raise DurationParseError("Duration cannot be empty")

    matches = list(_DURATION_PATTERN.finditer(text))
    if not matches or "".join(match.group(0).replace(" ", "") for match in matches) != text.replace(" ", ""):
        raise DurationParseError("Use a duration such as 30m, 2h, or 1d 4h")

    seconds = sum(int(match.group("value")) * _UNIT_SECONDS[match.group("unit")] for match in matches)
    if seconds <= 0:
        raise DurationParseError("Duration must be greater than zero")
    if maximum is not None and seconds > maximum:
        raise DurationParseError(f"Duration cannot exceed {humanize_duration(maximum)}")
    return seconds


def humanize_duration(seconds: int) -> str:
    """Format seconds as a compact human-readable duration."""
    if seconds < 0:
        raise ValueError("Duration cannot be negative")
    remaining = int(seconds)
    units = (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1))
    parts: list[str] = []
    for suffix, size in units:
        amount, remaining = divmod(remaining, size)
        if amount:
            parts.append(f"{amount}{suffix}")
    return "0s" if not parts else " ".join(parts)


def format_timestamp(seconds: int | float) -> str:
    """Return a Discord relative timestamp for a Unix timestamp."""
    return f"<t:{int(seconds)}:R>"


__all__ = ["DurationParseError", "format_timestamp", "humanize_duration", "parse_duration"]
