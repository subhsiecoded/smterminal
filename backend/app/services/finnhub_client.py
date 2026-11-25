"""Optional real-time overlay on top of the Yahoo-polling baseline.

Finnhub's free WebSocket pushes genuine, sub-second trade ticks - but only
for US-listed symbols on the free tier, and it needs an API key (free
signup at finnhub.io, no broker/KYC). This is entirely optional: with no
FINNHUB_API_KEY set, the app runs fine on Yahoo polling alone, just at
poll_interval_seconds freshness instead of tick-by-tick.

Plain WebSocket protocol (no SDK needed): connect, send
{"type":"subscribe","symbol":"AAPL"}, receive
{"type":"trade","data":[{"s":"AAPL","p":191.23,"v":100,"t":1699999999000}, ...]}.
"""

import asyncio
import json
import logging
from datetime import date, timedelta

import httpx
import websockets

logger = logging.getLogger("market_terminal.finnhub")

WS_URL = "wss://ws.finnhub.io?token={token}"
NEWS_URL = "https://finnhub.io/api/v1/company-news"


def looks_like_us_symbol(symbol: str) -> bool:
    """Finnhub's free WS tier is US-listed equities (plus crypto/forex with
    their own prefixed symbols, not handled here). A bare symbol with no
    exchange suffix/prefix (no '.', no ':') is the common case for US
    tickers in Yahoo's convention too (AAPL, MSFT - vs. ASML.AS, 7203.T).
    This is a heuristic, not a guarantee; Finnhub simply won't return data
    for a symbol it doesn't recognize, so a false positive just gets no ticks.
    """
    return "." not in symbol and ":" not in symbol and symbol.isupper()


async def get_company_news(api_key: str, symbol: str, days: int = 7) -> list[dict]:
    """Free on Finnhub's free tier (unlike real-time WS, which is US-only
    on free - this works for any symbol Finnhub recognizes). Returns a
    plain list of {headline, url, source, ts}; the caller decides what to
    do with an empty list (no news found vs. no key configured are
    distinguished by the router, not here).
    """
    to_date = date.today()
    from_date = to_date - timedelta(days=days)
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            NEWS_URL,
            params={"symbol": symbol, "from": from_date.isoformat(), "to": to_date.isoformat(), "token": api_key},
        )
        resp.raise_for_status()
        items = resp.json()

    return [
        {
            "headline": item.get("headline"),
            "url": item.get("url"),
            "source": item.get("source"),
            "ts": item.get("datetime"),  # Unix seconds
        }
        for item in items
        if item.get("headline") and item.get("url")
    ][:20]


async def stream(api_key: str, get_watched_symbols, on_tick) -> None:
    """Runs forever, reconnecting with backoff. `get_watched_symbols()` is
    called periodically to pick up newly-watched symbols without needing a
    restart; `on_tick(payload: dict)` is called for every trade.
    """
    backoff = 1.0
    subscribed: set[str] = set()

    while True:
        try:
            async with websockets.connect(WS_URL.format(token=api_key)) as ws:
                logger.info("Finnhub WS connected")
                backoff = 1.0
                subscribed.clear()

                async def resync_subscriptions():
                    while True:
                        wanted = {s for s in get_watched_symbols() if looks_like_us_symbol(s)}
                        for symbol in wanted - subscribed:
                            await ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                            subscribed.add(symbol)
                        for symbol in subscribed - wanted:
                            await ws.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
                            subscribed.discard(symbol)
                        await asyncio.sleep(5)

                resync_task = asyncio.create_task(resync_subscriptions())
                try:
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") != "trade":
                            continue
                        for trade in msg.get("data", []):
                            await on_tick(
                                {
                                    "symbol": trade["s"],
                                    "ltp": trade["p"],
                                    "volume": trade.get("v", 0),
                                    "ts": trade["t"] / 1000,
                                    "source": "stream",
                                }
                            )
                finally:
                    resync_task.cancel()
        except Exception as exc:  # noqa: BLE001 - any failure here just means "fall back to polling"
            logger.warning("Finnhub WS dropped (%s) - retrying in %.1fs, Yahoo polling continues meanwhile", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
