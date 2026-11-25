"""Shared symbol validation for watchlists, REST routes and WebSocket feeds."""

import re

# Command/category labels must never be treated as Yahoo tickers. This also
# protects old local watchlist files that may contain an accidental command.
RESERVED_SYMBOLS = {
    "INDIA-MOVERS", "INDIA", "SCREENER", "NSE", "MOVERS", "GAINERS", "LOSERS",
    "ACTIVE", "TURNOVER", "UNUSUAL-VOLUME", "TOP-GAINERS", "TOP-LOSERS",
    "MOST-ACTIVE", "VOLUME-SPIKE",
}
_SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=_-]{0,31}$")


def normalize_symbol(value: str) -> str | None:
    symbol = str(value or "").strip().upper()
    if not symbol or symbol in RESERVED_SYMBOLS or not _SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def is_market_symbol(value: str) -> bool:
    return normalize_symbol(value) is not None
