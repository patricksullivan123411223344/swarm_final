"""Environment-backed secrets accessor."""

from __future__ import annotations

import os


class Secrets:
    """Read required secrets from environment only."""

    @staticmethod
    def _required(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise EnvironmentError(f"Missing env var: {name}")
        return value

    @classmethod
    def get_exchange_api_key(cls, exchange_id: str) -> str:
        return cls._required(f"{exchange_id.upper()}_API_KEY")

    @classmethod
    def get_exchange_api_secret(cls, exchange_id: str) -> str:
        return cls._required(f"{exchange_id.upper()}_API_SECRET")

    @classmethod
    def get_db_dsn(cls) -> str:
        return cls._required("DATABASE_URL")

    @classmethod
    def get_redis_url(cls) -> str:
        return cls._required("REDIS_URL")
