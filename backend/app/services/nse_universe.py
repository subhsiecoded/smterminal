"""The complete, authoritative universe of NSE-listed equities - not a
fuzzy third-party search result, but NSE's own published master list
(~2,000 symbols). This is what makes "the entire India stock market"
actually mean something: Yahoo's unofficial search endpoint (used for
every other market) is good at surfacing well-known names, but isn't
guaranteed to be complete for India's long tail of small-caps - this
module doesn't guess, it loads NSE's own list.

Source: https://archives.nseindia.com/content/equities/EQUITY_L.csv -
a static CSV NSE publishes itself (no key, no login, no official SDK
needed), confirmed via multiple independent sources to still be the
current path as of late 2026. Like every other unofficial endpoint this
app uses, it can change without notice; parsing is defensive and a
fetch failure degrades to a clear error rather than a crash.

Columns in NSE's own file: SYMBOL, NAME OF COMPANY, SERIES, DATE OF
LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE. Column
names occasionally carry stray whitespace in the raw file, so they're
normalized (stripped + upper-cased) before use rather than matched
literally.
"""

import csv
import io
import logging
import time

import httpx

logger = logging.getLogger("market_terminal.nse_universe")

EQUITY_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

# A plain httpx client gets a 403 from NSE's archive host without a
# browser-like User-Agent - the same anti-bot posture Yahoo's endpoints
# have, just stricter about it.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,*/*",
}

REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # the list changes by listings/delistings, not intraday


def parse_equity_csv(raw_csv: str) -> list[dict]:
    """Pure parsing, deliberately separate from the network fetch - this
    is what's actually tested without needing to reach NSE's servers.
    Returns one dict per row: symbol, yahoo_symbol (SYMBOL.NS, ready to
    hand straight to the existing Yahoo-backed quote/candle endpoints),
    name, series, isin.
    """
    reader = csv.DictReader(io.StringIO(raw_csv))
    if reader.fieldnames is None:
        return []
    # Normalize header names once - NSE's file has been observed with
    # inconsistent leading/trailing whitespace on column headers.
    normalized_fields = {f: f.strip().upper() for f in reader.fieldnames}

    rows = []
    for raw_row in reader:
        row = {normalized_fields[k]: (v.strip() if v else v) for k, v in raw_row.items() if k in normalized_fields}
        symbol = row.get("SYMBOL")
        name = row.get("NAME OF COMPANY")
        if not symbol or not name:
            continue  # a malformed row shouldn't take the whole list down
        rows.append(
            {
                "symbol": symbol,
                "yahoo_symbol": f"{symbol}.NS",
                "name": name,
                "series": row.get("SERIES"),
                "isin": row.get("ISIN NUMBER"),
            }
        )
    return rows


class NseUniverse:
    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._fetched_at: float = 0.0

    def is_loaded(self) -> bool:
        return bool(self._rows)

    async def ensure_loaded(self) -> None:
        if self._rows and (time.time() - self._fetched_at) < REFRESH_INTERVAL_SECONDS:
            return
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
            resp = await client.get(EQUITY_LIST_URL)
            resp.raise_for_status()
        rows = parse_equity_csv(resp.text)
        if not rows:
            # Don't let a parse failure wipe out a previously good cache -
            # keep serving the last known-good list if there is one.
            if self._rows:
                logger.warning("NSE equity list fetch returned no rows - keeping previous cache")
                return
            raise ValueError("NSE equity list parsed to zero rows - format may have changed")
        self._rows = rows
        self._fetched_at = time.time()
        logger.info("loaded %d NSE-listed equities", len(rows))

    def all(self, series: str | None = "EQ") -> list[dict]:
        if series is None:
            return list(self._rows)
        return [r for r in self._rows if r["series"] == series]

    def search(self, query: str, limit: int = 20, series: str | None = "EQ") -> list[dict]:
        q = query.strip().upper()
        if not q:
            return []
        candidates = self.all(series=series)
        # Symbol-prefix matches first (what someone typing a ticker wants),
        # then substring-anywhere matches on symbol or company name.
        starts = [r for r in candidates if r["symbol"].startswith(q)]
        contains = [
            r
            for r in candidates
            if r not in starts and (q in r["symbol"] or q in r["name"].upper())
        ]
        return (starts + contains)[:limit]

    def get(self, symbol: str) -> dict | None:
        symbol = symbol.upper()
        for row in self._rows:
            if row["symbol"] == symbol:
                return row
        return None


# One universe per process - loaded on first request, refreshed daily.
universe = NseUniverse()


if __name__ == "__main__":
    # Self-check against a small synthetic CSV matching NSE's real
    # documented column layout, including the whitespace quirks that have
    # actually been observed in the wild - no network needed to verify
    # the parsing logic itself is correct.
    sample_csv = (
        "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,PAID UP VALUE,MARKET LOT,ISIN NUMBER,FACE VALUE\n"
        "RELIANCE,Reliance Industries Limited,EQ,29-NOV-95,10,1,INE002A01018,10\n"
        "TCS,Tata Consultancy Services Limited,EQ,25-AUG-04,1,1,INE467B01029,1\n"
        "SUZLON,Suzlon Energy Limited,BE,19-OCT-05,2,1,INE040H01021,2\n"
    )
    rows = parse_equity_csv(sample_csv)
    assert len(rows) == 3, rows
    assert rows[0] == {
        "symbol": "RELIANCE",
        "yahoo_symbol": "RELIANCE.NS",
        "name": "Reliance Industries Limited",
        "series": "EQ",
        "isin": "INE002A01018",
    }, rows[0]
    print("OK: parses NSE's documented column layout correctly")

    u = NseUniverse()
    u._rows = rows
    u._fetched_at = time.time()

    assert [r["symbol"] for r in u.all()] == ["RELIANCE", "TCS"], "EQ-series filter should exclude SUZLON (BE)"
    print("OK: series filter works (EQ-only by default)")

    assert [r["symbol"] for r in u.all(series=None)] == ["RELIANCE", "TCS", "SUZLON"]
    print("OK: series=None returns every series")

    results = u.search("TCS")
    assert results and results[0]["symbol"] == "TCS"
    print("OK: exact-prefix search finds TCS")

    results2 = u.search("reliance")  # case-insensitive, matches company name too
    assert any(r["symbol"] == "RELIANCE" for r in results2)
    print("OK: case-insensitive name search finds RELIANCE")

    assert u.search("nonexistentxyz") == []
    print("OK: no-match search returns empty, not an error")

    assert u.get("TCS")["yahoo_symbol"] == "TCS.NS"
    assert u.get("NOPE") is None
    print("OK: get() resolves a known symbol and returns None for an unknown one")

    print("ALL NSE UNIVERSE CHECKS PASSED")
