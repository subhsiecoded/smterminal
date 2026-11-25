import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from app.rate_limit import limiter
from app.services import yahoo_client
from app.services.nse_universe import universe as nse_universe

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("/search")
@limiter.limit("60/minute")
async def search_instruments(request: Request, q: str = Query(..., min_length=1)) -> list[dict]:
    """Search across every exchange Yahoo indexes - equities, ETFs, indices,
    crypto, FX - so the command palette can jump to literally any global
    ticker without a pre-seeded instruments table or a login.
    """
    try:
        return await yahoo_client.search(q)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail="Market data provider unreachable - try again shortly"
        ) from exc


@router.get("/india")
@limiter.limit("60/minute")
async def search_india(
    request: Request,
    q: str | None = Query(None, min_length=1, description="Search by symbol or company name"),
    series: str | None = Query("EQ", description="NSE series filter; pass empty to include all series"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """The complete, authoritative NSE equity universe (~2,000 symbols) -
    not a fuzzy search result but NSE's own published list (see
    services/nse_universe.py). Every `yahoo_symbol` returned here (e.g.
    "RELIANCE.NS") plugs directly into /api/market/quote, /candles,
    /indicators unchanged - same Yahoo-backed data path as everything else.

    With `q`: ranked search (symbol-prefix matches first) across the
    whole universe. Without it: a paginated browse of the full list, in
    NSE's own file order, via `limit`/`offset` - this is what makes
    "browse the entire India stock market" actually literal rather than
    just a search box.
    """
    series_filter = series or None
    try:
        await nse_universe.ensure_loaded()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="NSE's equity list is unreachable right now - try again shortly",
        ) from exc

    if q:
        results = nse_universe.search(q, limit=limit, series=series_filter)
        return {"total": len(results), "offset": 0, "limit": limit, "results": results}

    full = nse_universe.all(series=series_filter)
    page = full[offset : offset + limit]
    return {"total": len(full), "offset": offset, "limit": limit, "results": page}
