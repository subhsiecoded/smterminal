import httpx

from . import config


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str = config.API_BASE):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=8.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, _request_timeout: float | None = None, **params) -> dict | list:
        try:
            request_options = {"timeout": _request_timeout} if _request_timeout is not None else {}
            resp = await self._client.get(
                path,
                params={k: v for k, v in params.items() if v is not None},
                **request_options,
            )
        except httpx.TransportError as exc:
            raise ApiError(f"Can't reach the backend at {self._client.base_url} - is it running?") from exc
        if not resp.is_success:
            detail = resp.json().get("detail", resp.text) if resp.content else resp.text
            raise ApiError(str(detail), status_code=resp.status_code)
        return resp.json()

    async def get_quote(self, symbol: str) -> dict:
        return await self._get(f"/api/market/quote/{symbol}")

    async def get_quotes_batch(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        return await self._get("/api/market/quotes", symbols=",".join(symbols))

    async def get_candles(self, symbol: str, interval: str) -> list[dict]:
        return await self._get(f"/api/market/candles/{symbol}", interval=interval)

    async def get_indicators(self, symbol: str, interval: str) -> dict:
        return await self._get(f"/api/market/indicators/{symbol}", interval=interval)

    async def get_movers(self, category: str) -> list[dict]:
        return await self._get("/api/market/movers", category=category)

    async def get_india_screener(self, **params) -> dict:
        """NSE-wide quote scan can take longer than a normal single-symbol request."""
        return await self._get("/api/market/india/screener", _request_timeout=90.0, **params)

    async def get_news(self, symbol: str) -> dict:
        return await self._get(f"/api/market/news/{symbol}")

    async def search(self, query: str) -> list[dict]:
        return await self._get("/api/instruments/search", q=query)

    async def search_india(self, query: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        """The authoritative NSE equity universe (~2,000 symbols) - not
        Yahoo's fuzzy search. With no query, pages through the full list.
        """
        return await self._get("/api/instruments/india", q=query, limit=limit, offset=offset)
