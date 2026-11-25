import json
import time

from app.services.memory_store import store
from app.services.pubsub import broker

QUOTE_KEY = "quote:{symbol}"
HEARTBEAT_KEY = "last_tick_at:{symbol}"
STALE_AFTER_SECONDS = 10


def publish_quote(quote: dict, ttl_seconds: int = 5) -> None:
    """The single place a live price enters the system - used by the
    Yahoo poller, the optional Finnhub overlay, and an on-demand REST
    fallback fetch, so every caller gets identical caching/pub-sub/
    staleness behaviour regardless of where the price actually came from.
    """
    symbol = quote["symbol"]
    payload = json.dumps(quote)
    store.set(QUOTE_KEY.format(symbol=symbol), payload, ttl_seconds)
    broker.publish(f"ticks:{symbol}", payload)
    # Heartbeat TTL is generous (6x the stale threshold) - it just needs to
    # outlive the gap between ticks, not match the quote's own freshness.
    store.set(HEARTBEAT_KEY.format(symbol=symbol), time.time(), STALE_AFTER_SECONDS * 6)


def get_cached_quote(symbol: str) -> dict | None:
    raw = store.get(QUOTE_KEY.format(symbol=symbol))
    if raw is None:
        return None
    return json.loads(raw)


def get_staleness(symbol: str) -> dict:
    last = store.get(HEARTBEAT_KEY.format(symbol=symbol))
    if last is None:
        return {"symbol": symbol, "stale": True, "age_seconds": None}
    age = time.time() - float(last)
    return {"symbol": symbol, "stale": age > STALE_AFTER_SECONDS, "age_seconds": round(age, 1)}
