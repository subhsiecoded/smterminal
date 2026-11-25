import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import Settings, get_settings
from app.models.schemas import Candle, Quote
from app.rate_limit import limiter
from app.services import finnhub_client, indicators, market_data, yahoo_client
from app.services.india_screener import ScreenerUnavailable, screen_india
from app.services.cache import get_cached_quote, get_staleness, publish_quote
from app.services.memory_store import store
from app.services.candle_history import get_candle_snapshot
from app.services.watch_registry import registry
from app.services.symbols import normalize_symbol

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/quote/{symbol}", response_model=Quote)
@limiter.limit("120/minute")
async def get_quote(
    request: Request,
    symbol: str,
    settings: Settings = Depends(get_settings),
) -> Quote:
    symbol = normalize_symbol(symbol)
    if symbol is None:
        raise HTTPException(status_code=422, detail="Invalid ticker symbol (command labels are not market symbols)")
    registry.touch_rest_interest(symbol)  # keeps the poller refreshing this one

    cached = get_cached_quote(symbol)
    if cached:
        return Quote(**cached)

    # First time anyone's asked for this symbol - fetch it immediately
    # instead of making the caller wait for the next poll cycle.
    try:
        quotes = await market_data.get_quotes([symbol])
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail="Market data provider unreachable - try again shortly"
        ) from exc
    quote = quotes.get(symbol)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"No quote found for '{symbol}'")
    publish_quote(quote, ttl_seconds=settings.quote_cache_ttl_seconds)
    return Quote(**quote)


@router.get("/quotes", response_model=list[Quote])
@limiter.limit("60/minute")
async def get_quotes_batch(
    request: Request,
    symbols: str = Query(..., description="Comma-separated symbols, e.g. AAPL,MSFT,TCS.NS"),
    settings: Settings = Depends(get_settings),
) -> list[Quote]:
    """Batch endpoint for a whole watchlist in one round trip instead of N
    separate /quote calls - this is what the TUI watchlist actually uses.
    """
    wanted = [s for raw in symbols.split(",") if (s := normalize_symbol(raw))][:50]
    for s in wanted:
        registry.touch_rest_interest(s)

    out: dict[str, dict] = {}
    missing = []
    for s in wanted:
        cached = get_cached_quote(s)
        if cached:
            out[s] = cached
        else:
            missing.append(s)

    if missing:
        try:
            fetched = await market_data.get_quotes(missing)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise HTTPException(
                status_code=503, detail="Market data provider unreachable - try again shortly"
            ) from exc
        for symbol, quote in fetched.items():
            publish_quote(quote, ttl_seconds=settings.quote_cache_ttl_seconds)
            out[symbol] = quote

    return [Quote(**out[s]) for s in wanted if s in out]


@router.get("/quote/{symbol}/staleness")
async def get_quote_staleness(symbol: str) -> dict:
    return get_staleness(symbol.upper())


@router.get("/candles/{symbol}", response_model=list[Candle])
@limiter.limit("60/minute")
async def get_candles(
    request: Request,
    symbol: str,
    interval: str = Query("5m", pattern="^(1m|5m|15m|1h|1d|1w)$"),
) -> list[Candle]:
    """Historical OHLCV fetched directly from the provider on demand -
    there's no pre-seeded local candle store to keep in sync for every
    possible global ticker, so this is cached briefly in memory rather
    than persisted in Postgres. (If you want your own durable OHLCV
    warehouse later, the `candles` table from migration 0001 is still
    there to write into from here.)
    """
    symbol = normalize_symbol(symbol)
    if symbol is None:
        raise HTTPException(status_code=422, detail="Invalid ticker symbol (command labels are not market symbols)")
    try:
        candles = await get_candle_snapshot(symbol, interval)
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Market data provider temporarily unavailable; retry later"
        ) from exc
    if not candles:
        raise HTTPException(status_code=404, detail=f"No candle data found for '{symbol}'")
    return [Candle(**row) for row in candles]


@router.get("/movers")
@limiter.limit("30/minute")
async def get_movers(
    request: Request,
    category: str = Query("gainers", pattern="^(gainers|losers|active)$"),
) -> list[dict]:
    """US-market day gainers/losers/most-active - best-effort against
    Yahoo's undocumented screener endpoint (see yahoo_client.get_movers's
    docstring); cached briefly since this is a "browse" feature, not
    something that needs sub-10-second freshness.
    """
    cache_key = f"movers:{category}"
    cached = store.get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        movers = await yahoo_client.get_movers(category)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail="Market data provider unreachable - try again shortly"
        ) from exc

    settings = get_settings()
    store.set(cache_key, json.dumps(movers), max(settings.quote_cache_ttl_seconds, 15))
    return movers


@router.get("/india/screener")
@limiter.limit("15/minute")
async def get_india_screener(
    request: Request,
    category: str = Query("gainers", pattern="^(gainers|losers|active|turnover|unusual-volume|all)$"),
    series: str = Query("EQ", description="NSE series: EQ by default, ALL to include every series"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    min_change_pct: float | None = Query(None, ge=-100, le=1000),
    max_change_pct: float | None = Query(None, ge=-100, le=1000),
    min_volume: int | None = Query(None, ge=0),
    min_turnover: float | None = Query(None, ge=0, description="Approximate INR turnover: price × reported volume"),
    min_relative_volume: float | None = Query(None, ge=0),
    sort_by: str | None = Query(None, pattern="^(change_pct|volume|turnover|relative_volume|ltp|market_cap|symbol)$"),
    order: str = Query("auto", pattern="^(auto|asc|desc)$"),
    refresh: bool = Query(False, description="Bypass the 60-second snapshot cache"),
) -> dict:
    """Scan the NSE equity universe and rank available Yahoo quote snapshots.

    This is intentionally separate from /movers, which retains its existing
    global/US screener behavior. The NSE scan is cached and uses bounded
    concurrent batches to avoid uncontrolled upstream request bursts.
    """
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price cannot exceed max_price")
    if min_change_pct is not None and max_change_pct is not None and min_change_pct > max_change_pct:
        raise HTTPException(status_code=422, detail="min_change_pct cannot exceed max_change_pct")

    series_filter = None if series.upper() in ("ALL", "*") else series.upper()
    try:
        return await screen_india(
            category=category,
            series=series_filter,
            limit=limit,
            offset=offset,
            refresh=refresh,
            min_price=min_price,
            max_price=max_price,
            min_change_pct=min_change_pct,
            max_change_pct=max_change_pct,
            min_volume=min_volume,
            min_turnover=min_turnover,
            min_relative_volume=min_relative_volume,
            sort_by=sort_by,
            order=order,
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, ScreenerUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "India screener unavailable") from exc


@router.get("/indicators/{symbol}")
@limiter.limit("60/minute")
async def get_indicators(
    request: Request,
    symbol: str,
    interval: str = Query("1d", pattern="^(1m|5m|15m|1h|1d|1w)$"),
) -> dict:
    """SMA(20)/EMA(12)/EMA(26)/RSI(14) computed server-side from candle
    closes (see services/indicators.py) - real math over real history,
    not a canned number.
    """
    symbol = normalize_symbol(symbol)
    if symbol is None:
        raise HTTPException(status_code=422, detail="Invalid ticker symbol (command labels are not market symbols)")
    try:
        candles = await get_candle_snapshot(symbol, interval)
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Market data provider temporarily unavailable; retry later"
        ) from exc
    if not candles:
        raise HTTPException(status_code=404, detail=f"No candle data found for '{symbol}'")

    closes = [c["close"] for c in candles]
    return {"symbol": symbol, "interval": interval, **indicators.compute_all(closes)}


@router.get("/news/{symbol}")
@limiter.limit("30/minute")
async def get_news(request: Request, symbol: str) -> dict:
    """Company news - needs FINNHUB_API_KEY (free tier includes this, even
    without the real-time WS overlay). Returns a clear "not configured"
    flag rather than an empty list indistinguishable from "no news found,"
    so the TUI can tell the two apart.
    """
    settings = get_settings()
    if not settings.finnhub_api_key:
        return {"configured": False, "items": []}
    try:
        items = await finnhub_client.get_company_news(settings.finnhub_api_key, symbol.upper())
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail="News provider unreachable - try again shortly"
        ) from exc
    return {"configured": True, "items": items}
