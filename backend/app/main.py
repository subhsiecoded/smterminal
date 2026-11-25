import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.rate_limit import limiter
from app.routers import instruments, market, orders, trading_mode, watchlists
from app.security import RequestContextMiddleware, SecurityHeadersMiddleware, logger
from app.services import coingecko_client, poller, yahoo_client
from app.services.watch_registry import registry
from app.ws.gateway import router as ws_router

settings = get_settings()
background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The Yahoo poller runs unconditionally - it's the zero-config real-time
    # baseline and needs no API key, no Redis, nothing external at all.
    # The Finnhub overlay only starts if a key is configured; with none,
    # the app runs on polling alone.
    background_tasks.append(
        asyncio.create_task(poller.run(settings.poll_interval_seconds, settings.quote_cache_ttl_seconds))
    )
    if settings.finnhub_api_key:
        from app.services import finnhub_client
        from app.services.cache import publish_quote

        async def on_tick(tick: dict) -> None:
            publish_quote(tick, ttl_seconds=settings.quote_cache_ttl_seconds)

        background_tasks.append(
            asyncio.create_task(
                finnhub_client.stream(settings.finnhub_api_key, registry.active_symbols, on_tick)
            )
        )
        logger.info("Finnhub real-time overlay enabled")
    else:
        logger.info("No FINNHUB_API_KEY set - running on Yahoo polling only (fine, just not tick-level)")

    yield

    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    background_tasks.clear()
    await yahoo_client.close()


app = FastAPI(title="Market Terminal API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Live-Intent-Token"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error("unhandled_exception request_id=%s error=%s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


app.include_router(market.router)
app.include_router(instruments.router)
app.include_router(orders.router)       # still login-gated - dormant until you re-enable auth
app.include_router(watchlists.router)   # still login-gated - dormant until you re-enable auth
app.include_router(trading_mode.router)
app.include_router(ws_router)


@app.get("/api/health")
async def health() -> dict:
    # No external services to check anymore - the only way this process
    # answers at all is if its own event loop is alive, which a 200
    # response already proves. "status" stays simple rather than faking a
    # dependency check that doesn't exist.
    return {
        "status": "ok",
        "finnhub_overlay": bool(settings.finnhub_api_key),
        "watched_symbols": len(registry.active_symbols()),
    }

async def _probe_provider(name: str) -> dict:
    """Small opt-in connectivity probe used only by /api/health/providers."""
    try:
        if name == "yahoo":
            quotes = await yahoo_client.get_quotes(["RELIANCE.NS"])
            received = "RELIANCE.NS" in quotes
        elif name == "coingecko":
            quotes = await coingecko_client.get_quotes(["BTC-USD"])
            received = "BTC-USD" in quotes
        else:
            return {"status": "not_probed"}
        return {"status": "ok" if received else "no_quote", "quote_received": received}
    except httpx.HTTPStatusError as exc:
        status = "rate_limited" if exc.response.status_code == 429 else "error"
        return {"status": status, "http_status": exc.response.status_code}
    except Exception as exc:  # noqa: BLE001 - health output must not break the API
        return {"status": "error", "error_type": type(exc).__name__}


@app.get("/api/health/providers", tags=["health"])
async def provider_health(probe: bool = False) -> dict:
    """Show data-provider configuration; with probe=true, test Yahoo and CoinGecko.

    This route is intended for Swagger/UI diagnostics. The normal /api/health
    endpoint remains a fast process-liveness check and makes no upstream calls.
    """
    payload = {
        "status": "ok",
        "probe_requested": probe,
        "providers": {
            "yahoo_finance": {
                "status": "not_probed",
                "role": "NSE/global equity quotes, candles and global movers",
                "note": "Unofficial best-effort endpoint; not exchange-certified live data.",
            },
            "coingecko": {
                "status": "not_probed",
                "role": "Aggregated crypto quotes, with Yahoo fallback",
            },
            "finnhub": {
                "status": "configured" if settings.finnhub_api_key else "not_configured",
                "role": "Optional streaming/news overlay",
            },
        },
    }
    if probe:
        yahoo_result, coingecko_result = await asyncio.gather(
            _probe_provider("yahoo"), _probe_provider("coingecko")
        )
        payload["providers"]["yahoo_finance"].update(yahoo_result)
        payload["providers"]["coingecko"].update(coingecko_result)
        states = {yahoo_result.get("status"), coingecko_result.get("status")}
        payload["status"] = "ok" if states <= {"ok"} else "degraded"
    return payload

