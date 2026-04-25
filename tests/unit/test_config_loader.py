"""Tests for configuration loader behavior."""

from __future__ import annotations

from pathlib import Path

from config.loader import get, load_config


def _write_config(tmp_path: Path, strategy_content: str = "") -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "defaults.yaml").write_text(
        "risk:\n"
        "  max_daily_drawdown_pct: 0.05\n"
        "signals:\n"
        "  min_confluence_score: 3\n",
        encoding="utf-8",
    )
    (config_dir / "strategy.yaml").write_text(strategy_content, encoding="utf-8")


def test_load_config_uses_defaults(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    assert cfg["risk"]["max_daily_drawdown_pct"] == 0.05
    assert get("signals.min_confluence_score") == 3


def test_load_config_applies_strategy_override(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path, "risk:\n  max_daily_drawdown_pct: 0.04\n")
    monkeypatch.chdir(tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    assert cfg["risk"]["max_daily_drawdown_pct"] == 0.04


def test_get_missing_key_returns_default(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    load_config.cache_clear()
    assert get("nonexistent.key", default="fallback") == "fallback"
