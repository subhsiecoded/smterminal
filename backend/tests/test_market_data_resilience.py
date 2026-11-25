import asyncio

import pytest

from app.models.schemas import Quote
from app.services import market_data


def test_quote_schema_accepts_fractional_aggregated_volume():
    quote = Quote(
        symbol="BTC-USD", ltp=90000, change_pct=1.2,
        volume=39207329622.987785, volume_unit="USD notional (24h)",
        ts="2026-11-24T10:00:00Z",
    )
    assert quote.volume == 39207329622.987785
    assert quote.volume_unit == "USD notional (24h)"


@pytest.mark.asyncio
async def test_coingecko_failure_falls_back_without_losing_equity_quotes(monkeypatch):
    async def bad_crypto(symbols):
        raise RuntimeError("CoinGecko rate limited")

    async def yahoo_quotes(symbols):
        assert set(symbols) == {"RELIANCE.NS", "BTC-USD"}
        return {
            "RELIANCE.NS": {"symbol": "RELIANCE.NS", "ltp": 1500},
            "BTC-USD": {"symbol": "BTC-USD", "ltp": 90000},
        }

    monkeypatch.setattr(market_data.coingecko_client, "get_quotes", bad_crypto)
    monkeypatch.setattr(market_data.yahoo_client, "get_quotes", yahoo_quotes)

    result = await market_data.get_quotes(["RELIANCE.NS", "BTC-USD"])
    assert set(result) == {"RELIANCE.NS", "BTC-USD"}


@pytest.mark.asyncio
async def test_coingecko_success_survives_yahoo_failure(monkeypatch):
    async def crypto_quotes(symbols):
        return {"BTC-USD": {"symbol": "BTC-USD", "ltp": 90000}}

    async def bad_yahoo(symbols):
        raise RuntimeError("Yahoo unavailable")

    monkeypatch.setattr(market_data.coingecko_client, "get_quotes", crypto_quotes)
    monkeypatch.setattr(market_data.yahoo_client, "get_quotes", bad_yahoo)

    result = await market_data.get_quotes(["BTC-USD", "RELIANCE.NS"])
    assert set(result) == {"BTC-USD"}


@pytest.mark.asyncio
async def test_all_provider_failures_raise(monkeypatch):
    async def bad_crypto(symbols):
        raise RuntimeError("CoinGecko unavailable")

    async def bad_yahoo(symbols):
        raise RuntimeError("Yahoo unavailable")

    monkeypatch.setattr(market_data.coingecko_client, "get_quotes", bad_crypto)
    monkeypatch.setattr(market_data.yahoo_client, "get_quotes", bad_yahoo)

    with pytest.raises(RuntimeError, match="Yahoo unavailable"):
        await market_data.get_quotes(["BTC-USD"])


def test_normalize_symbol_accepts_nvidia_company_name_alias():
    from app.services.symbols import normalize_symbol

    assert normalize_symbol("NVIDIA") == "NVDA"
    assert normalize_symbol("NVIDIA Corporation") == "NVDA"


@pytest.mark.asyncio
async def test_candle_snapshot_coalesces_concurrent_requests(monkeypatch):
    import asyncio
    from app.services import candle_history
    from app.services.memory_store import store

    key = "candles:NVDA:1d"
    stale_key = "candles:last:NVDA:1d"
    store.delete(key)
    store.delete(stale_key)
    calls = 0
    candles = [{"ts": 1, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}]

    async def fake_get_candles(symbol, interval):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return candles

    monkeypatch.setattr(candle_history.yahoo_client, "get_candles", fake_get_candles)
    try:
        first, second = await asyncio.gather(
            candle_history.get_candle_snapshot("NVDA", "1d", fresh_ttl=30),
            candle_history.get_candle_snapshot("NVDA", "1d", fresh_ttl=30),
        )
        assert first == candles
        assert second == candles
        assert calls == 1
    finally:
        store.delete(key)
        store.delete(stale_key)


@pytest.mark.asyncio
async def test_candle_snapshot_serves_last_good_snapshot_on_provider_failure(monkeypatch):
    from app.services import candle_history
    from app.services.memory_store import store
    import json
    import httpx

    key = "candles:NVDA:1d"
    stale_key = "candles:last:NVDA:1d"
    store.delete(key)
    candles = [{"ts": 1, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}]
    store.set(stale_key, json.dumps(candles), 3600)

    async def failed_get_candles(symbol, interval):
        raise httpx.ConnectError("provider unavailable")

    monkeypatch.setattr(candle_history.yahoo_client, "get_candles", failed_get_candles)
    try:
        result = await candle_history.get_candle_snapshot("NVDA", "1d", fresh_ttl=30)
        assert result == candles
    finally:
        store.delete(key)
        store.delete(stale_key)
