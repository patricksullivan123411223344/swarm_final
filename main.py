"""Bootstrap entrypoint for Phase 0.1."""

from __future__ import annotations

import asyncio

from config.loader import load_config
from infrastructure.database import DatabaseConnection
from infrastructure.redis_client import RedisClient
from infrastructure.secrets import Secrets


async def bootstrap() -> None:
    """Validate config and infrastructure lifecycle wiring."""
    _ = load_config()
    database = DatabaseConnection(dsn=Secrets.get_db_dsn())
    redis_client = RedisClient(url=Secrets.get_redis_url())
    await database.connect()
    await redis_client.connect()
    await redis_client.disconnect()
    await database.disconnect()


if __name__ == "__main__":
    asyncio.run(bootstrap())
