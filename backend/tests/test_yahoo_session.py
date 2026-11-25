import json

import httpx
import pytest

from app.services import yahoo_client


@pytest.mark.asyncio
async def test_quote_client_bootstraps_cookie_and_crumb(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "fc.yahoo.com":
            return httpx.Response(404, headers={"Set-Cookie": "A1=session-cookie; Domain=.yahoo.com; Path=/"})
        if request.url.path.endswith("/v1/test/getcrumb"):
            return httpx.Response(200, text="crumb-123")
        if request.url.path.endswith("/v7/finance/quote"):
            assert request.url.params.get("crumb") == "crumb-123"
            assert "A1=session-cookie" in request.headers.get("cookie", "")
            return httpx.Response(200, json={"quoteResponse": {"result": [{
                "symbol": "RELIANCE.NS", "regularMarketPrice": 1500.0,
                "regularMarketChange": 15.0, "regularMarketChangePercent": 1.0,
                "regularMarketVolume": 12345,
            }]}})
        raise AssertionError(f"unexpected URL: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=yahoo_client._BASE_HEADERS)
    monkeypatch.setattr(yahoo_client, "_http_client", client)
    monkeypatch.setattr(yahoo_client, "_crumb", None)
    monkeypatch.setattr(yahoo_client, "_crumb_expires_at", 0.0)

    try:
        result = await yahoo_client.get_quotes(["RELIANCE.NS"])
        assert result["RELIANCE.NS"]["ltp"] == 1500.0
        assert any(req.url.host == "fc.yahoo.com" for req in calls)
        assert any(req.url.path.endswith("/v1/test/getcrumb") for req in calls)
    finally:
        await client.aclose()
        monkeypatch.setattr(yahoo_client, "_http_client", None)
        monkeypatch.setattr(yahoo_client, "_crumb", None)


@pytest.mark.asyncio
async def test_quote_client_refreshes_expired_crumb_after_401(monkeypatch):
    crumb_calls = 0
    quote_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal crumb_calls, quote_calls
        if request.url.host == "fc.yahoo.com":
            return httpx.Response(404, headers={"Set-Cookie": "A1=session-cookie; Domain=.yahoo.com; Path=/"})
        if request.url.path.endswith("/v1/test/getcrumb"):
            crumb_calls += 1
            return httpx.Response(200, text=f"crumb-{crumb_calls}")
        if request.url.path.endswith("/v7/finance/quote"):
            quote_calls += 1
            if request.url.params.get("crumb") == "crumb-1":
                return httpx.Response(401, json={"error": "Invalid Crumb"})
            return httpx.Response(200, json={"quoteResponse": {"result": []}})
        raise AssertionError(f"unexpected URL: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=yahoo_client._BASE_HEADERS)
    monkeypatch.setattr(yahoo_client, "_http_client", client)
    monkeypatch.setattr(yahoo_client, "_crumb", None)
    monkeypatch.setattr(yahoo_client, "_crumb_expires_at", 0.0)

    try:
        assert await yahoo_client.get_quotes(["RELIANCE.NS"]) == {}
        assert crumb_calls == 2
        assert quote_calls == 2
    finally:
        await client.aclose()
        monkeypatch.setattr(yahoo_client, "_http_client", None)
        monkeypatch.setattr(yahoo_client, "_crumb", None)
