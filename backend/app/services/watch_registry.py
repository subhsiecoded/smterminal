import time

from app.services.symbols import normalize_symbol


REST_INTEREST_TTL_SECONDS = 60


class WatchRegistry:
    """Tracks which symbols are worth actively polling/streaming right now:
    anything a connected WS client has subscribed to, plus anything fetched
    via the REST quote endpoint in the last minute (so a one-off lookup
    still gets fresh follow-up polls for a little while without requiring
    a live socket). Single-process, in-memory - fine for this build's scale;
    a multi-process deployment would move this to a Redis set instead.
    """

    def __init__(self) -> None:
        self._ws_refcounts: dict[str, int] = {}
        self._rest_interest: dict[str, float] = {}

    def add_ws_interest(self, symbol: str) -> None:
        normalized = normalize_symbol(symbol)
        if normalized is None:
            return
        self._ws_refcounts[normalized] = self._ws_refcounts.get(normalized, 0) + 1

    def remove_ws_interest(self, symbol: str) -> None:
        normalized = normalize_symbol(symbol)
        if normalized and normalized in self._ws_refcounts:
            self._ws_refcounts[normalized] -= 1
            if self._ws_refcounts[normalized] <= 0:
                del self._ws_refcounts[normalized]

    def touch_rest_interest(self, symbol: str) -> None:
        normalized = normalize_symbol(symbol)
        if normalized is None:
            return
        self._rest_interest[normalized] = time.time() + REST_INTEREST_TTL_SECONDS

    def active_symbols(self) -> set[str]:
        now = time.time()
        expired = [s for s, exp in self._rest_interest.items() if exp <= now]
        for s in expired:
            del self._rest_interest[s]
        return set(self._ws_refcounts) | set(self._rest_interest)


# One registry per process, shared by the gateway, the market router, and
# the background poller/overlay tasks started in main.py's lifespan.
registry = WatchRegistry()
