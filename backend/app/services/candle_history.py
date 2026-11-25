"""Shared, resilient candle-history retrieval for market and indicator APIs."""

import asyncio
import json
import logging

import httpx

from app.config import get_settings
from app.services import yahoo_client
from app.services.memory_store import store

logger = logging.getLogger("market_terminal.market")
_candle_locks: dict[str, asyncio.Lock] = {}
_STALE_CANDLE_TTL_SECONDS = 24 * 60 * 60


async def get_candle_snapshot(symbol: str, interval: str, fresh_ttl: int | None = None) -> list[dict]:
    """Read-through candle cache with stale-on-provider-error fallback.

    The lock coalesces concurrent chart and indicator requests for the same
    symbol/interval into a single Yahoo request. A last-known snapshot is kept
    for one day so a temporary provider outage does not blank the chart.
    """
    settings = get_settings()
    ttl = max(15, int(fresh_ttl or settings.candle_cache_ttl_seconds))
    cache_key = f"candles:{symbol}:{interval}"
    stale_key = f"candles:last:{symbol}:{interval}"

    def read_cached(key: str) -> list[dict] | None:
        raw = store.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, list) and payload else None
        except (TypeError, json.JSONDecodeError):
            store.delete(key)
            return None

    cached = read_cached(cache_key)
    if cached is not None:
        return cached

    lock = _candle_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        cached = read_cached(cache_key)
        if cached is not None:
            return cached

        try:
            candles = await yahoo_client.get_candles(symbol, interval)
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            stale = read_cached(stale_key)
            if stale is not None:
                logger.warning("serving stale candles for %s/%s after provider failure (%s)", symbol, interval, type(exc).__name__)
                return stale
            raise

        if not candles:
            stale = read_cached(stale_key)
            return stale if stale is not None else []

        serialized = json.dumps(candles)
        store.set(cache_key, serialized, ttl)
        store.set(stale_key, serialized, _STALE_CANDLE_TTL_SECONDS)
        return candles
