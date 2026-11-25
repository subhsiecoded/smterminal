# Currently unused by the live request path - market.py fetches candles
# directly from the provider now (see its docstring) rather than from a
# pre-seeded local table. Kept as a building block for later: e.g. a worker
# that persists your own OHLCV history, or a re-added broker integration.

import asyncpg
from fastapi import Depends

from app.config import Settings, get_settings

_pool: asyncpg.Pool | None = None


async def init_pool(settings: Settings) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    return _pool


async def get_pool(settings: Settings = Depends(get_settings)) -> asyncpg.Pool:
    return await init_pool(settings)
