"""Exchange client bridge around CCXT."""

from __future__ import annotations

from typing import Any

import ccxt.async_support as ccxt


class ExchangeClient:
    """Stateful exchange wrapper with explicit lifecycle."""

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
    ) -> None:
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._client: Any = None

    async def connect(self) -> None:
        exchange_cls = getattr(ccxt, self._exchange_id)
        self._client = exchange_cls(
            {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "enableRateLimit": True,
            }
        )
        if self._testnet and hasattr(self._client, "set_sandbox_mode"):
            self._client.set_sandbox_mode(True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Exchange client not connected. Call connect() first.")
        return self._client
