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
