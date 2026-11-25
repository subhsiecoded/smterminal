"""Thin client for Yahoo Finance's public, unauthenticated endpoints.

These are unofficial - not a documented, licensed API, and Yahoo can change
or rate-limit them without notice. They're used here because they're the
only genuinely zero-config way to get search/quote/candle data across
global exchanges without an API key, a broker account, or a login - which
is exactly the point of this build right now. If you later need an SLA or
heavier volume, swap this module for a licensed provider (Finnhub, Polygon,
Twelve Data, ...) behind the same three functions; nothing else in the app
needs to change.
"""

import logging
import time
import asyncio
import math

import httpx

logger = logging.getLogger("market_terminal.yahoo")

_BASE_HEADERS = {
    # An unauthenticated User-Agent is more likely to be rate-limited/blocked
    # than a normal browser UA - this isn't spoofing identity, just not
    # announcing "I am a bare HTTP client" to a free, undocumented endpoint.
    "User-Agent": "Mozilla/5.0 (compatible; market-terminal/1.0)"
}

SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
BOOTSTRAP_URL = "https://fc.yahoo.com/"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
CRUMB_TTL_SECONDS = 15 * 60

# Reuse one cookie jar for the Yahoo session. The v7 quote endpoint now
# commonly returns HTTP 401 unless the request carries a session cookie and
# the matching crumb. The v8 chart endpoint remains a separate path.
_http_client: httpx.AsyncClient | None = None
_crumb: str | None = None
_crumb_expires_at = 0.0
_crumb_lock = asyncio.Lock()


def _session_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(headers=_BASE_HEADERS, timeout=12.0, follow_redirects=True)
    return _http_client


async def _get_crumb(*, force: bool = False, stale_crumb: str | None = None) -> str:
    """Create/reuse a Yahoo cookie+crumb session for crumb-protected v7 APIs."""
    global _crumb, _crumb_expires_at
    if stale_crumb and _crumb and _crumb != stale_crumb and time.time() < _crumb_expires_at:
        return _crumb
    if not force and _crumb and time.time() < _crumb_expires_at:
        return _crumb

    async with _crumb_lock:
        # Several parallel screener batches may all receive a 401 for the same
        # old crumb. Only the first needs to refresh it; the rest reuse it.
        if stale_crumb and _crumb and _crumb != stale_crumb and time.time() < _crumb_expires_at:
            return _crumb
        if not force and _crumb and time.time() < _crumb_expires_at:
            return _crumb

        client = _session_client()
        # fc.yahoo.com establishes the A1 session cookie. It may return a
        # non-200 status while still setting cookies, so do not require 200.
        try:
            await client.get(BOOTSTRAP_URL)
        except httpx.HTTPError as exc:
            logger.warning("Yahoo cookie bootstrap request failed: %s", exc)

        response = await client.get(CRUMB_URL)
        response.raise_for_status()
        crumb = response.text.strip()
        if not crumb or crumb.startswith("{") or "unauthorized" in crumb.lower():
            raise httpx.HTTPStatusError(
                "Yahoo did not return a usable session crumb",
                request=response.request,
                response=response,
            )
        _crumb = crumb
        _crumb_expires_at = time.time() + CRUMB_TTL_SECONDS
        return crumb


async def _quote_response(symbols: list[str]) -> dict:
    """Call Yahoo v7 quote with a valid cookie/crumb pair, refreshing once on 401."""
    client = _session_client()
    crumb = await _get_crumb()
    response = await client.get(QUOTE_URL, params={"symbols": ",".join(symbols), "crumb": crumb})
    if response.status_code == 401:
        # Crumbs are bound to their cookie jar and can expire/revoke early.
        crumb = await _get_crumb(force=True, stale_crumb=crumb)
        response = await client.get(QUOTE_URL, params={"symbols": ",".join(symbols), "crumb": crumb})
    response.raise_for_status()
    return response.json()


def error_summary(exc: Exception) -> str:
    """Return provider diagnostics without leaking session cookies or crumb query parameters."""
    if isinstance(exc, httpx.HTTPStatusError):
        request = exc.request
        response = exc.response
        return f"HTTP {response.status_code} from {request.url.host}{request.url.path}"
    return f"{type(exc).__name__}: {str(exc)[:180]}"


async def close() -> None:
    """Close the shared Yahoo HTTP session during FastAPI shutdown."""
    global _http_client, _crumb, _crumb_expires_at
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None
    _crumb = None
    _crumb_expires_at = 0.0

# category -> Yahoo's own predefined screener id. These best-effort endpoints
# are called with the same cookie/crumb session as quote requests.
_MOVER_SCREENER_IDS = {
    "gainers": "day_gainers",
    "losers": "day_losers",
    "active": "most_actives",
}

# Our interval names -> Yahoo's chart API interval + how far back "range" goes.
# Yahoo limits how much history you can pull at fine resolutions (e.g. 1m
# data is capped to the last ~7 days) - this maps our UI's choices to
# ranges that are actually valid.
_INTERVAL_MAP: dict[str, tuple[str, str]] = {
    "1m": ("1m", "5d"),
    "5m": ("5m", "1mo"),
    "15m": ("15m", "1mo"),
    "1h": ("60m", "3mo"),
    "1d": ("1d", "2y"),
    "1w": ("1wk", "5y"),
}


async def search(query: str, limit: int = 10) -> list[dict]:
    """Global symbol search across every exchange Yahoo indexes - this is
    what makes "entire world stocks" possible with zero setup.
    """
    async with httpx.AsyncClient(headers=_BASE_HEADERS, timeout=5.0) as client:
        resp = await client.get(SEARCH_URL, params={"q": query, "quotesCount": limit, "newsCount": 0})
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("quotes", []):
        symbol = item.get("symbol")
        if not symbol:
            continue
        results.append(
            {
                "symbol": symbol,
                "name": item.get("shortname") or item.get("longname") or symbol,
                "exchange": item.get("exchange"),
                "type": item.get("quoteType"),
            }
        )
    return results


async def get_quotes(symbols: list[str]) -> dict[str, dict]:
    """Batch quote fetch - one HTTP call for the whole watchlist, not one
    per symbol. Returns a dict keyed by symbol; a symbol Yahoo doesn't
    recognize is simply absent from the result rather than raising.
    """
    if not symbols:
        return {}
    data = await _quote_response(symbols)

    out: dict[str, dict] = {}
    for row in data.get("quoteResponse", {}).get("result", []):
        symbol = row.get("symbol")
        if not symbol:
            continue
        price = row.get("regularMarketPrice")
        if price is None:
            continue
        out[symbol] = {
            "symbol": symbol,
            "ltp": price,
            "change": row.get("regularMarketChange", 0.0),
            "change_pct": row.get("regularMarketChangePercent", 0.0),
            "volume": row.get("regularMarketVolume"),
            "volume_unit": "shares",
            "average_volume_10d": row.get("averageDailyVolume10Day"),
            "average_volume_3m": row.get("averageDailyVolume3Month"),
            "market_cap": row.get("marketCap"),
            "day_high": row.get("regularMarketDayHigh"),
            "day_low": row.get("regularMarketDayLow"),
            "open": row.get("regularMarketOpen"),
            "previous_close": row.get("regularMarketPreviousClose"),
            "fifty_two_week_high": row.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": row.get("fiftyTwoWeekLow"),
            # Top-of-book only - Yahoo's free feed has no real depth-of-market.
            # Present for many (mostly US) tickers, absent for plenty of
            # international ones; the caller treats missing fields as
            # "not available," never fabricates them.
            "bid": row.get("bid"),
            "ask": row.get("ask"),
            "bid_size": row.get("bidSize"),
            "ask_size": row.get("askSize"),
            "currency": row.get("currency"),
            "exchange": row.get("fullExchangeName") or row.get("exchange"),
            "source": "poll",
            "ts": time.time(),
        }
    return out


async def get_movers(category: str, count: int = 10) -> list[dict]:
    """Day gainers/losers/most-active, US market - Yahoo's predefined
    screener endpoint. This one's reverse-engineered from observed behavior
    rather than documented: the response shape is best-effort-parsed, and
    this returns an empty list rather than raising if Yahoo changes it,
    so a broken movers panel degrades quietly instead of taking the rest
    of the app down with it.
    """
    screener_id = _MOVER_SCREENER_IDS.get(category)
    if screener_id is None:
        raise ValueError(f"Unknown mover category '{category}' - expected one of {list(_MOVER_SCREENER_IDS)}")

    client = _session_client()
    crumb = await _get_crumb()
    resp = await client.get(
        SCREENER_URL,
        params={"scrIds": screener_id, "count": count, "formatted": "false", "crumb": crumb},
    )
    if resp.status_code == 401:
        crumb = await _get_crumb(force=True, stale_crumb=crumb)
        resp = await client.get(
            SCREENER_URL,
            params={"scrIds": screener_id, "count": count, "formatted": "false", "crumb": crumb},
        )
    resp.raise_for_status()
    data = resp.json()

    try:
        quotes = data["finance"]["result"][0].get("quotes", [])
    except (KeyError, IndexError, TypeError):
        logger.warning("movers response for '%s' didn't match the expected shape - returning empty", category)
        return []

    out = []
    for q in quotes:
        price = q.get("regularMarketPrice")
        if price is None:
            continue
        out.append(
            {
                "symbol": q.get("symbol"),
                "name": q.get("shortName") or q.get("longName") or q.get("symbol"),
                "price": price,
                "change_pct": q.get("regularMarketChangePercent", 0.0),
                "volume": q.get("regularMarketVolume"),
            }
        )
    return out


def _parse_candles_payload(data: dict) -> list[dict]:
    """Normalize Yahoo chart data and safely discard incomplete OHLC bars."""
    if not isinstance(data, dict):
        return []
    chart_root = data.get("chart")
    if not isinstance(chart_root, dict):
        return []
    results = chart_root.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return []

    chart = results[0]
    timestamps = chart.get("timestamp")
    indicators = chart.get("indicators")
    quote_sections = indicators.get("quote") if isinstance(indicators, dict) else None
    quote = quote_sections[0] if isinstance(quote_sections, list) and quote_sections and isinstance(quote_sections[0], dict) else {}
    if not isinstance(timestamps, list):
        return []

    fields = {name: quote.get(name) if isinstance(quote.get(name), list) else []
              for name in ("open", "high", "low", "close", "volume")}

    def finite_number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    candles = []
    for index, timestamp in enumerate(timestamps):
        values = [finite_number(fields[name][index]) if index < len(fields[name]) else None
                  for name in ("open", "high", "low", "close")]
        if any(value is None for value in values):
            continue  # Yahoo pads gaps (halts, pre-market) with nulls.
        try:
            ts = int(timestamp)
        except (TypeError, ValueError, OverflowError):
            continue
        volume = finite_number(fields["volume"][index]) if index < len(fields["volume"]) else 0
        candles.append({
            "ts": ts,
            "open": values[0],
            "high": values[1],
            "low": values[2],
            "close": values[3],
            "volume": max(0, int(volume or 0)),
        })
    return candles


async def get_candles(symbol: str, interval: str) -> list[dict]:
    yahoo_interval, yahoo_range = _INTERVAL_MAP.get(interval, ("1d", "1y"))
    async with httpx.AsyncClient(headers=_BASE_HEADERS, timeout=8.0) as client:
        resp = await client.get(
            CHART_URL.format(symbol=symbol),
            params={"interval": yahoo_interval, "range": yahoo_range},
        )
        resp.raise_for_status()
        data = resp.json()
    return _parse_candles_payload(data)
