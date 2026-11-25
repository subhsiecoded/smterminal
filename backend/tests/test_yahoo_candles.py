from app.services.yahoo_client import _parse_candles_payload


def test_yahoo_candle_parser_skips_null_and_non_finite_bars():
    payload = {
        "chart": {
            "result": [{
                "timestamp": [100, 200, 300, 400],
                "indicators": {"quote": [{
                    "open": [10, None, 12, float("nan")],
                    "high": [11, None, 13, 14],
                    "low": [9, None, 11, 12],
                    "close": [10.5, None, 12.5, 13],
                    "volume": [100, None, 250, 300],
                }]},
            }]
        }
    }
    candles = _parse_candles_payload(payload)
    assert candles == [{
        "ts": 100,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 100,
    }, {
        "ts": 300,
        "open": 12.0,
        "high": 13.0,
        "low": 11.0,
        "close": 12.5,
        "volume": 250,
    }]


def test_yahoo_candle_parser_handles_missing_quote_section():
    assert _parse_candles_payload({"chart": {"result": [{"timestamp": [1], "indicators": {"quote": []}}]}}) == []
    assert _parse_candles_payload({"chart": {"result": []}}) == []
    assert _parse_candles_payload({}) == []
