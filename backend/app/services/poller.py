import asyncio
import logging

from app.services import market_data, yahoo_client
from app.services.cache import publish_quote
from app.services.watch_registry import registry

logger = logging.getLogger("market_terminal.poller")


async def run(interval_seconds: float, cache_ttl_seconds: int) -> None:
    """Runs for the lifetime of the app (started in main.py's lifespan).
    Each tick: snapshot whatever symbols currently have real interest
    (watched over WS, or hit via REST in the last minute - see
    watch_registry.py), fetch them in as few batched calls as possible
    (one to Yahoo, one to CoinGecko if any crypto symbols are watched -
    see market_data.py), and publish each through the same path a
    genuine push tick would use. An idle server with nobody watching
    anything makes zero outbound calls.
    """
    base_delay = max(float(interval_seconds), 1.0)
    retry_delay = base_delay
    while True:
        symbols = list(registry.active_symbols())
        if not symbols:
            retry_delay = base_delay
            await asyncio.sleep(base_delay)
            continue
        try:
            quotes = await market_data.get_quotes(symbols)
            for quote in quotes.values():
                publish_quote(quote, ttl_seconds=cache_ttl_seconds)
            retry_delay = base_delay
        except Exception as exc:  # noqa: BLE001 - one bad poll shouldn't kill the loop
            # Avoid hammering a blocked upstream and flooding the logs with the
            # same 401/429 on every normal polling interval. The next retry is
            # at most once per minute while the provider is failing.
            logger.warning(
                "poll failed for %d symbols (%s) - retrying in %.0fs",
                len(symbols), yahoo_client.error_summary(exc), min(max(retry_delay * 2, base_delay), 60.0),
            )
            retry_delay = min(max(retry_delay * 2, base_delay), 60.0)
            await asyncio.sleep(retry_delay)
            continue
        await asyncio.sleep(base_delay)
