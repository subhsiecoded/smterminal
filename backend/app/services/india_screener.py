"""Best-effort NSE-wide equity screener.

The universe is sourced from NSE's published equity master list. Quotes are
retrieved from Yahoo Finance's unofficial quote endpoint in bounded batches.
This is suitable for personal research, not an exchange-grade live feed or
execution system. Partial provider coverage is reported explicitly.
"""

import asyncio
import json
import logging
import math
import time
from typing import Any

import httpx

from app.services import yahoo_client
from app.services.memory_store import store
from app.services.nse_universe import universe

logger = logging.getLogger("market_terminal.india_screener")

CACHE_KEY_PREFIX = "india-screener:"
CACHE_TTL_SECONDS = 60
MIN_FORCE_RESCAN_SECONDS = 20
BATCH_SIZE = 100
MAX_CONCURRENT_BATCHES = 2
_scan_lock = asyncio.Lock()


class ScreenerUnavailable(Exception):
    """Raised when no usable market quotes could be retrieved."""


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _enrich_rows(universe_rows: list[dict], quote_map: dict[str, dict]) -> list[dict]:
    """Join NSE identity data to Yahoo quote snapshots and derive metrics."""
    output: list[dict] = []
    for instrument in universe_rows:
        yahoo_symbol = instrument["yahoo_symbol"]
        quote = quote_map.get(yahoo_symbol)
        if not quote:
            continue

        price = _finite_number(quote.get("ltp"))
        if price is None:
            continue
        volume = _finite_number(quote.get("volume"))
        avg_volume = _finite_number(quote.get("average_volume_10d"))
        if not avg_volume:
            avg_volume = _finite_number(quote.get("average_volume_3m"))

        change_pct = _finite_number(quote.get("change_pct")) or 0.0
        volume_value = max(int(volume or 0), 0)
        turnover = price * volume_value
        relative_volume = (volume_value / avg_volume) if avg_volume and avg_volume > 0 else None
        day_high = _finite_number(quote.get("day_high"))
        day_low = _finite_number(quote.get("day_low"))
        day_range_position = None
        if day_high is not None and day_low is not None and day_high > day_low:
            day_range_position = round(max(0.0, min(100.0, (price - day_low) / (day_high - day_low) * 100)), 1)

        output.append({
            "symbol": yahoo_symbol,
            "nse_symbol": instrument["symbol"],
            "name": instrument.get("name") or instrument["symbol"],
            "series": instrument.get("series"),
            "isin": instrument.get("isin"),
            "ltp": price,
            "change": _finite_number(quote.get("change")) or 0.0,
            "change_pct": change_pct,
            "volume": volume_value,
            "turnover": round(turnover, 2),
            "average_volume": int(avg_volume) if avg_volume else None,
            "relative_volume": round(relative_volume, 2) if relative_volume is not None else None,
            "market_cap": _finite_number(quote.get("market_cap")),
            "day_high": day_high,
            "day_low": day_low,
            "day_range_position_pct": day_range_position,
            "open": _finite_number(quote.get("open")),
            "previous_close": _finite_number(quote.get("previous_close")),
            "fifty_two_week_high": _finite_number(quote.get("fifty_two_week_high")),
            "fifty_two_week_low": _finite_number(quote.get("fifty_two_week_low")),
            "currency": quote.get("currency") or "INR",
            "exchange": quote.get("exchange") or "NSE",
            "quote_ts": quote.get("ts"),
        })
    return output


async def _fetch_snapshot(rows: list[dict]) -> tuple[list[dict], int]:
    symbols = [row["yahoo_symbol"] for row in rows]
    chunks = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    failed_batches = 0
    quote_map: dict[str, dict] = {}

    async def fetch_one(batch: list[str]) -> dict[str, dict]:
        nonlocal failed_batches
        async with semaphore:
            try:
                return await yahoo_client.get_quotes(batch)
            except Exception as exc:
                failed_batches += 1
                logger.warning(
                    "NSE screener quote batch failed (%d symbols): %s",
                    len(batch), yahoo_client.error_summary(exc),
                )
                return {}

    results = await asyncio.gather(*(fetch_one(chunk) for chunk in chunks))
    for result in results:
        quote_map.update(result)

    return _enrich_rows(rows, quote_map), failed_batches


async def _load_snapshot(series: str | None, force_refresh: bool = False) -> dict:
    cache_key = CACHE_KEY_PREFIX + (series or "ALL")
    cached = store.get(cache_key)
    if cached:
        cached_snapshot = json.loads(cached)
        age = time.time() - cached_snapshot.get("scanned_at", 0)
        if not force_refresh or age < MIN_FORCE_RESCAN_SECONDS:
            return cached_snapshot

    async with _scan_lock:
        # A concurrent request may have populated the cache while this one waited.
        cached = store.get(cache_key)
        if cached:
            cached_snapshot = json.loads(cached)
            age = time.time() - cached_snapshot.get("scanned_at", 0)
            if not force_refresh or age < MIN_FORCE_RESCAN_SECONDS:
                return cached_snapshot

        await universe.ensure_loaded()
        instruments = universe.all(series=series)
        if not instruments:
            raise ScreenerUnavailable("NSE equity universe is empty")

        rows, failed_batches = await _fetch_snapshot(instruments)
        if not rows:
            raise ScreenerUnavailable(
                "No NSE quotes returned by the upstream provider. The provider may be unavailable or rate-limiting requests."
            )

        snapshot = {
            "rows": rows,
            "universe_total": len(instruments),
            "quote_count": len(rows),
            "failed_batches": failed_batches,
            "scanned_at": time.time(),
            "series": series or "ALL",
        }
        store.set(cache_key, json.dumps(snapshot), CACHE_TTL_SECONDS)
        return snapshot


def _matches_filters(
    item: dict,
    *,
    category: str,
    min_price: float | None,
    max_price: float | None,
    min_change_pct: float | None,
    max_change_pct: float | None,
    min_volume: int | None,
    min_turnover: float | None,
    min_relative_volume: float | None,
) -> bool:
    price = item["ltp"]
    change = item["change_pct"]
    volume = item["volume"]
    turnover = item["turnover"]
    relative = item["relative_volume"]

    if min_price is not None and price < min_price:
        return False
    if max_price is not None and price > max_price:
        return False
    if min_change_pct is not None and change < min_change_pct:
        return False
    if max_change_pct is not None and change > max_change_pct:
        return False
    if min_volume is not None and volume < min_volume:
        return False
    if min_turnover is not None and turnover < min_turnover:
        return False
    if min_relative_volume is not None and (relative is None or relative < min_relative_volume):
        return False
    if category == "gainers" and change <= 0:
        return False
    if category == "losers" and change >= 0:
        return False
    if category == "unusual-volume" and relative is None:
        return False
    return True


def rank_snapshot(
    snapshot: dict,
    *,
    category: str = "gainers",
    limit: int = 50,
    offset: int = 0,
    min_price: float | None = None,
    max_price: float | None = None,
    min_change_pct: float | None = None,
    max_change_pct: float | None = None,
    min_volume: int | None = None,
    min_turnover: float | None = None,
    min_relative_volume: float | None = None,
    sort_by: str | None = None,
    order: str = "auto",
) -> dict:
    """Pure filter/rank/page function; can be tested without network access."""
    categories = {"gainers", "losers", "active", "turnover", "unusual-volume", "all"}
    if category not in categories:
        raise ValueError(f"Unsupported category: {category}")

    if category == "unusual-volume" and min_relative_volume is None:
        min_relative_volume = 1.5

    filtered = [item for item in snapshot["rows"] if _matches_filters(
        item,
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_change_pct=min_change_pct,
        max_change_pct=max_change_pct,
        min_volume=min_volume,
        min_turnover=min_turnover,
        min_relative_volume=min_relative_volume,
    )]

    default_sort = {
        "gainers": "change_pct",
        "losers": "change_pct",
        "active": "volume",
        "turnover": "turnover",
        "unusual-volume": "relative_volume",
        "all": "change_pct",
    }[category]
    sort_key = sort_by or default_sort
    valid_sort_keys = {
        "change_pct", "volume", "turnover", "relative_volume", "ltp", "market_cap", "symbol"
    }
    if sort_key not in valid_sort_keys:
        raise ValueError(f"sort_by must be one of {sorted(valid_sort_keys)}")

    if order == "auto":
        reverse = not (category == "losers" and sort_key == "change_pct")
    else:
        reverse = order == "desc"
    if sort_key == "symbol":
        filtered.sort(key=lambda item: item["symbol"], reverse=reverse)
    else:
        present = [item for item in filtered if item.get(sort_key) is not None]
        missing = [item for item in filtered if item.get(sort_key) is None]
        present.sort(key=lambda item: item.get(sort_key), reverse=reverse)
        filtered = present + missing

    total = len(filtered)
    page = filtered[offset:offset + limit]
    scanned_at = snapshot.get("scanned_at")
    age_seconds = max(round(time.time() - scanned_at, 1), 0) if scanned_at else None
    universe_total = snapshot.get("universe_total", 0)
    quote_count = snapshot.get("quote_count", len(snapshot["rows"]))
    all_changes = [float(row.get("change_pct") or 0) for row in snapshot["rows"]]
    advancers = sum(change > 0 for change in all_changes)
    decliners = sum(change < 0 for change in all_changes)
    unchanged = sum(change == 0 for change in all_changes)

    return {
        "results": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "category": category,
        "sort_by": sort_key,
        "order": "desc" if reverse else "asc",
        "meta": {
            "universe_total": universe_total,
            "quote_count": quote_count,
            "coverage_pct": round((quote_count / universe_total) * 100, 1) if universe_total else 0,
            "advancers": advancers,
            "decliners": decliners,
            "unchanged": unchanged,
            "advance_decline_ratio": round(advancers / decliners, 2) if decliners else None,
            "failed_batches": snapshot.get("failed_batches", 0),
            "scanned_at": scanned_at,
            "age_seconds": age_seconds,
            "series": snapshot.get("series", "EQ"),
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "provider": "Yahoo Finance unofficial quote endpoint",
            "data_note": "Best-effort market snapshots; not an exchange-certified real-time feed. Quote availability and delay vary by instrument.",
        },
    }


async def screen_india(
    *,
    category: str = "gainers",
    series: str | None = "EQ",
    limit: int = 50,
    offset: int = 0,
    refresh: bool = False,
    min_price: float | None = None,
    max_price: float | None = None,
    min_change_pct: float | None = None,
    max_change_pct: float | None = None,
    min_volume: int | None = None,
    min_turnover: float | None = None,
    min_relative_volume: float | None = None,
    sort_by: str | None = None,
    order: str = "auto",
) -> dict:
    snapshot = await _load_snapshot(series, force_refresh=refresh)
    return rank_snapshot(
        snapshot,
        category=category,
        limit=limit,
        offset=offset,
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
