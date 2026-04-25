"""Async HTTP client bridge."""

from __future__ import annotations

from typing import Any

import httpx


class AsyncHTTPClient:
    """Stateful pooled HTTP client wrapper."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_connections: int = 50,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_connections = max_connections
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_seconds),
            limits=httpx.Limits(max_connections=self._max_connections),
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("HTTP client not connected. Call connect() first.")
        return self._client
