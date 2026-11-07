"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    bot_token: str
    database_url: str
    bot_owner_id: int | None
    environment: str
    log_level: str
    dev_guild_ids: tuple[int, ...]

    @classmethod
    def from_environment(cls) -> "Settings":
        token = os.getenv("BOT_TOKEN", "").strip()
        database_url = os.getenv("DATABASE_URL", "").strip()
        owner_raw = os.getenv("BOT_OWNER_ID", "").strip()
        owner_id = int(owner_raw) if owner_raw else None

        guild_ids: list[int] = []
        for value in os.getenv("DEV_GUILD_IDS", "").split(","):
            value = value.strip()
            if value:
                guild_ids.append(int(value))

        return cls(
            bot_token=token,
            database_url=database_url,
            bot_owner_id=owner_id,
            environment=os.getenv("ENVIRONMENT", "development").strip().lower(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper().strip(),
            dev_guild_ids=tuple(guild_ids),
        )

    def validate(self) -> None:
        """Fail early with actionable errors for required production settings."""
        missing: list[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variable(s): {names}")


settings = Settings.from_environment()
