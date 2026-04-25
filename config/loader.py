"""Configuration loading and access helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge nested dictionaries recursively."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    env_map = {
        "TRADING_MODE": ("runtime", "trading_mode"),
        "APP_ENV": ("runtime", "app_env"),
    }
    merged = dict(config)
    for env_name, key_path in env_map.items():
        env_val = os.getenv(env_name)
        if env_val is None:
            continue
        node = merged
        for segment in key_path[:-1]:
            node = node.setdefault(segment, {})
        node[key_path[-1]] = env_val
    return merged


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Load defaults, apply strategy overrides, then env overrides."""
    defaults = _read_yaml(Path("config/defaults.yaml"))
    strategy = _read_yaml(Path("config/strategy.yaml"))
    merged = deep_merge(defaults, strategy)
    return _apply_env_overrides(merged)


def get(key_path: str, default: Any = None) -> Any:
    """Fetch a config value using dot-notation path."""
    value: Any = load_config()
    for segment in key_path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return default
        value = value[segment]
    return value
