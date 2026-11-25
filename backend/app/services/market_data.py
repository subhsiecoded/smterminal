"""Provider routing with partial-failure isolation.

NSE/global equities are fetched from Yahoo. Recognized crypto pairs prefer
CoinGecko, but a CoinGecko 429 must not cancel the entire watchlist poll. On
CoinGecko failure we fall back to Yahoo for those crypto symbols. If one
provider remains healthy, its quotes are returned even when another provider
is degraded.
"""

import logging

import httpx

from app.services import coingecko_client, yahoo_client

logger = logging.getLogger("market_terminal.market_data")


def _error_summary(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from {exc.request.url.host}{exc.request.url.path}"
    return f"{type(exc).__name__}: {str(exc)[:160]}"


async def get_quotes(symbols: list[str]) -> dict[str, dict]:
    """Return available quotes while isolating provider-level failures.

    A failed crypto provider no longer discards successful NSE/equity quotes.
    If CoinGecko is unavailable, crypto tickers are retried through Yahoo.
    An exception is raised only when every required provider path fails and no
    quote could be returned, allowing the REST API/poller to report a real
    upstream outage rather than a misleading empty success.
    """
    if not symbols:
        return {}

    crypto = [s for s in symbols if coingecko_client.supports(s)]
    equities = [s for s in symbols if not coingecko_client.supports(s)]
    out: dict[str, dict] = {}
    failures: list[tuple[str, Exception]] = []

    if crypto:
        try:
            out.update(await coingecko_client.get_quotes(crypto))
        except Exception as exc:  # noqa: BLE001 - deliberately isolate the provider
            failures.append(("CoinGecko", exc))
            logger.warning(
                "CoinGecko quote request failed for %d symbols (%s); falling back to Yahoo",
                len(crypto), _error_summary(exc),
            )
            equities.extend(crypto)

    if equities:
        try:
            out.update(await yahoo_client.get_quotes(equities))
        except Exception as exc:  # noqa: BLE001 - crypto may still have succeeded
            failures.append(("Yahoo Finance", exc))
            logger.warning(
                "Yahoo quote request failed for %d symbols (%s)",
                len(equities), _error_summary(exc),
            )

    if failures and not out:
        # Raise the last provider failure (normally the fallback attempt) so
        # the caller can return 503 / back off instead of reporting false data.
        provider, exc = failures[-1]
        logger.error("all market-data paths failed; last failure from %s", provider)
        raise exc

    if failures:
        failed_names = ", ".join(name for name, _ in failures)
        logger.warning(
            "partial market-data result: %d/%d quotes returned; degraded provider(s): %s",
            len(out), len(symbols), failed_names,
        )

    return out
