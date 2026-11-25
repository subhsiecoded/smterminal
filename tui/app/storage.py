import json
import re

from . import config


_RESERVED = {
    "INDIA-MOVERS", "INDIA", "SCREENER", "NSE", "MOVERS", "GAINERS", "LOSERS",
    "ACTIVE", "TURNOVER", "UNUSUAL-VOLUME", "TOP-GAINERS", "TOP-LOSERS",
    "MOST-ACTIVE", "VOLUME-SPIKE",
}
_SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=_-]{0,31}$")


def _clean_symbols(symbols: list[str]) -> list[str]:
    cleaned = []
    for value in symbols:
        symbol = str(value).strip().upper()
        if symbol and symbol not in _RESERVED and _SYMBOL_RE.fullmatch(symbol) and symbol not in cleaned:
            cleaned.append(symbol)
    return cleaned


def load_watchlist() -> list[str]:
    try:
        raw = config.WATCHLIST_FILE.read_text()
        symbols = json.loads(raw)
        if isinstance(symbols, list) and all(isinstance(s, str) for s in symbols):
            cleaned = _clean_symbols(symbols)
            if cleaned:
                if cleaned != [s.upper() for s in symbols]:
                    save_watchlist(cleaned)  # migrate polluted/duplicate legacy files once
                return cleaned
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return _clean_symbols(list(config.DEFAULT_SYMBOLS))


def save_watchlist(symbols: list[str]) -> None:
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        config.WATCHLIST_FILE.write_text(json.dumps(sorted(set(_clean_symbols(symbols)))))
    except OSError:
        pass  # best-effort - a failed save just means it falls back to defaults next launch
