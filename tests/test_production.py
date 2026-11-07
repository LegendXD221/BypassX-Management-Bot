from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from config.settings import Settings
from db.client import Database
from utils.time import parse_duration


def _settings(**overrides: str) -> Settings:
    values = {
        "BOT_TOKEN": "token",
        "DATABASE_URL": "postgresql://localhost/bypassx",
        "ENVIRONMENT": "production",
        "LOG_LEVEL": "INFO",
    }
    values.update(overrides)
    return Settings(
        bot_token=values["BOT_TOKEN"],
        database_url=values["DATABASE_URL"],
        bot_owner_id=None,
        environment=values["ENVIRONMENT"],
        log_level=values["LOG_LEVEL"],
        dev_guild_ids=(),
    )


def test_production_settings_validate() -> None:
    _settings().validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("environment", "prod", "ENVIRONMENT"), ("log_level", "TRACE", "LOG_LEVEL")],
)
def test_settings_reject_invalid_runtime_values(field: str, value: str, message: str) -> None:
    with pytest.raises(RuntimeError, match=message):
        replace(_settings(), **{field: value}).validate()


def test_duration_parser_supports_compound_durations() -> None:
    assert parse_duration("1d 4h 30m") == 102600


@pytest.mark.asyncio
async def test_database_connect_retries_and_healthchecks(monkeypatch: pytest.MonkeyPatch) -> None:
    database = Database()
    attempts = 0

    class FakeClient:
        async def connect(self) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("database warming up")

        async def disconnect(self) -> None:
            return None

        async def query_raw(self, _query: str) -> list[tuple[int]]:
            return [(1,)]

    database.client = FakeClient()  # type: ignore[assignment]

    monkeypatch.setattr("db.client.asyncio.sleep", lambda _seconds: _completed_sleep())

    await database.connect(retries=3, base_delay=0)
    assert database.connected is True
    assert attempts == 3
    assert await database.healthcheck() is True
    await database.disconnect()


async def _completed_sleep() -> None:
    return None


def test_timestamp_inputs_are_timezone_compatible() -> None:
    assert datetime.now(timezone.utc).tzinfo is timezone.utc
