"""A plain in-process, in-memory key-value store with per-key TTLs -
replaces Redis for everything this app used it for except pub/sub (see
pubsub.py for that half). This is correct specifically because the whole
backend runs as a single Python process: the poller, the optional Finnhub
overlay, the WS gateway, and every HTTP request all share one event loop
and therefore one instance of this store. It would NOT be correct across
multiple processes/replicas - there's no cross-process sharing here, by
design, in exchange for needing zero external services.

No locks: asyncio is cooperative within one thread, so a dict access here
is never preempted mid-operation the way a multi-threaded cache would need
guarding against.
"""

import time


class ExpiringCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: object, ttl_seconds: float) -> None:
        self._store[key] = (time.time() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


# One store per process, shared by cache.py and the market router.
store = ExpiringCache()
