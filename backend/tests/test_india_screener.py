from app.services.india_screener import _enrich_rows, rank_snapshot


def sample_snapshot():
    return {
        "universe_total": 4,
        "quote_count": 3,
        "failed_batches": 1,
        "scanned_at": 1_800_000_000,
        "series": "EQ",
        "rows": [
            {"symbol": "AAA.NS", "nse_symbol": "AAA", "name": "Alpha", "ltp": 100.0,
             "change_pct": 5.0, "volume": 500_000, "turnover": 50_000_000,
             "relative_volume": 2.5, "market_cap": 5_000_000_000},
            {"symbol": "BBB.NS", "nse_symbol": "BBB", "name": "Beta", "ltp": 50.0,
             "change_pct": -3.0, "volume": 900_000, "turnover": 45_000_000,
             "relative_volume": 0.8, "market_cap": 1_000_000_000},
            {"symbol": "CCC.NS", "nse_symbol": "CCC", "name": "Gamma", "ltp": 25.0,
             "change_pct": 1.0, "volume": 1_500_000, "turnover": 37_500_000,
             "relative_volume": 3.0, "market_cap": 2_000_000_000},
        ],
    }


def test_gainers_and_losers_sort_in_correct_direction():
    snapshot = sample_snapshot()
    gainers = rank_snapshot(snapshot, category="gainers")
    losers = rank_snapshot(snapshot, category="losers")
    assert [row["symbol"] for row in gainers["results"]] == ["AAA.NS", "CCC.NS"]
    assert [row["symbol"] for row in losers["results"]] == ["BBB.NS"]


def test_active_and_turnover_rank_highest_first():
    snapshot = sample_snapshot()
    active = rank_snapshot(snapshot, category="active")
    turnover = rank_snapshot(snapshot, category="turnover")
    assert active["results"][0]["symbol"] == "CCC.NS"
    assert turnover["results"][0]["symbol"] == "AAA.NS"


def test_filters_and_pagination_are_applied_after_scan():
    result = rank_snapshot(
        sample_snapshot(), category="all", min_price=20, min_change_pct=0,
        min_volume=400_000, limit=1, offset=1,
    )
    assert result["total"] == 2
    assert len(result["results"]) == 1
    assert result["results"][0]["symbol"] == "CCC.NS"


def test_unusual_volume_uses_relative_volume_threshold():
    result = rank_snapshot(sample_snapshot(), category="unusual-volume")
    assert [row["symbol"] for row in result["results"]] == ["CCC.NS", "AAA.NS"]


def test_coverage_metadata_is_explicit():
    result = rank_snapshot(sample_snapshot(), category="all")
    assert result["meta"]["coverage_pct"] == 75.0
    assert result["meta"]["failed_batches"] == 1
    assert result["meta"]["advancers"] == 2
    assert result["meta"]["decliners"] == 1


def test_nse_identity_is_joined_to_quote_and_relative_volume_is_derived():
    rows = [{
        "symbol": "RELIANCE", "yahoo_symbol": "RELIANCE.NS",
        "name": "Reliance Industries Limited", "series": "EQ", "isin": "INE002A01018",
    }]
    quotes = {
        "RELIANCE.NS": {
            "ltp": 1500, "change": 30, "change_pct": 2.0, "volume": 2_000_000,
            "average_volume_10d": 1_000_000, "currency": "INR", "exchange": "NSE",
        }
    }
    enriched = _enrich_rows(rows, quotes)
    assert enriched[0]["nse_symbol"] == "RELIANCE"
    assert enriched[0]["isin"] == "INE002A01018"
    assert enriched[0]["turnover"] == 3_000_000_000
    assert enriched[0]["relative_volume"] == 2.0


def test_scan_uses_cached_snapshot_between_refreshes(monkeypatch):
    import asyncio

    from app.services import india_screener
    from app.services.memory_store import store

    instruments = [{
        "symbol": "RELIANCE", "yahoo_symbol": "RELIANCE.NS",
        "name": "Reliance Industries Limited", "series": "EQ", "isin": "INE002A01018",
    }]
    calls = {"count": 0}

    async def fake_ensure_loaded():
        return None

    async def fake_quotes(symbols):
        calls["count"] += 1
        return {
            "RELIANCE.NS": {
                "ltp": 1500, "change": 30, "change_pct": 2.0, "volume": 2_000_000,
                "average_volume_10d": 1_000_000, "currency": "INR", "exchange": "NSE",
            }
        }

    monkeypatch.setattr(india_screener.universe, "ensure_loaded", fake_ensure_loaded)
    monkeypatch.setattr(india_screener.universe, "all", lambda series="EQ": instruments)
    monkeypatch.setattr(india_screener.yahoo_client, "get_quotes", fake_quotes)
    store.delete("india-screener:EQ")

    async def run_twice():
        first = await india_screener.screen_india(category="gainers")
        second = await india_screener.screen_india(category="losers")
        return first, second

    first, second = asyncio.run(run_twice())
    assert calls["count"] == 1
    assert first["results"][0]["symbol"] == "RELIANCE.NS"
    assert second["results"] == []
    store.delete("india-screener:EQ")


def test_reserved_market_command_is_not_a_symbol():
    from app.services.symbols import normalize_symbol

    assert normalize_symbol("INDIA-MOVERS") is None
    assert normalize_symbol("SCREENER") is None
    assert normalize_symbol("RELIANCE.NS") == "RELIANCE.NS"
    assert normalize_symbol("^NSEI") == "^NSEI"


def test_watch_registry_ignores_reserved_command_symbols():
    from app.services.watch_registry import WatchRegistry

    registry = WatchRegistry()
    registry.add_ws_interest("INDIA-MOVERS")
    registry.touch_rest_interest("INDIA-MOVERS")
    registry.add_ws_interest("RELIANCE.NS")
    assert registry.active_symbols() == {"RELIANCE.NS"}
