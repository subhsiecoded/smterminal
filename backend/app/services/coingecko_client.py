"""CoinGecko's public API needs no key at all - not even a free signup -
and aggregates price across many exchanges, which is generally more
representative for crypto than a single-venue quote. Used here as the
more-accurate path for recognized crypto tickers; Yahoo remains the
fallback for anything not in SYMBOL_TO_ID.
"""

import time

import httpx

SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"

# Yahoo's convention (BTC-USD) -> CoinGecko's own id scheme. Extend this as
# needed; a symbol not listed here just falls through to Yahoo instead.
SYMBOL_TO_ID = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
    "XRP-USD": "ripple",
    "DOGE-USD": "dogecoin",
    "ADA-USD": "cardano",
    "AVAX-USD": "avalanche-2",
    "LINK-USD": "chainlink",
    "LTC-USD": "litecoin",
    "DOT-USD": "polkadot",
}


def supports(symbol: str) -> bool:
    return symbol.upper() in SYMBOL_TO_ID


async def get_quotes(symbols: list[str]) -> dict[str, dict]:
    ids = {SYMBOL_TO_ID[s.upper()] for s in symbols if s.upper() in SYMBOL_TO_ID}
    if not ids:
        return {}

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            SIMPLE_PRICE_URL,
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    id_to_symbol = {v: k for k, v in SYMBOL_TO_ID.items()}
    out: dict[str, dict] = {}
    for coin_id, values in data.items():
        symbol = id_to_symbol.get(coin_id)
        price = values.get("usd")
        if symbol is None or price is None:
            continue
        change_pct = values.get("usd_24h_change", 0.0)
        out[symbol] = {
            "symbol": symbol,
            "ltp": price,
            "change": price * change_pct / 100 if change_pct else 0.0,
            "change_pct": change_pct,
            "volume": values.get("usd_24h_vol"),
            "volume_unit": "USD notional (24h)",
            "bid": None,
            "ask": None,
            "bid_size": None,
            "ask_size": None,
            "currency": "USD",
            "exchange": "CoinGecko (aggregated)",
            "source": "poll",
            "ts": time.time(),
        }
    return out
