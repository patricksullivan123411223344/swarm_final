"""Tests for environment-backed secrets accessor."""

import pytest

from infrastructure.secrets import Secrets


def test_get_exchange_api_key_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "abc123")
    assert Secrets.get_exchange_api_key("binance") == "abc123"


def test_get_exchange_api_secret_missing_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    with pytest.raises(EnvironmentError, match="BINANCE_API_SECRET"):
        Secrets.get_exchange_api_secret("binance")


def test_get_db_dsn_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        Secrets.get_db_dsn()
