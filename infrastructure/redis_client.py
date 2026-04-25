"""Redis client bridge."""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis


class RedisClient:
    """Stateful Redis connection wrapper."""

    def __init__(self, url: str, max_connections: int = 20) -> None:
        self._url = url
        self._max_connections = max_connections
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=self._max_connections,
        )
        await self._client.ping()

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Redis is not connected. Call connect() first.")
        return self._client
