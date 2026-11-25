# Free API keys - what's used here, and what else is out there

Everything below is free with no credit card required to sign up, as of
researching this in November 2026. Free tiers change without much notice,
so verify current limits on the provider's own site before depending on
one - these numbers are a starting point, not a promise.

**The app needs none of these to run.** The two it actually uses by
default (Yahoo, CoinGecko) require no signup at all. Everything else in
this table is either already wired in as an *optional* upgrade, or listed
as a credible alternative if you outgrow what's here.

| Provider | Free tier (Nov 2026) | Signup | Used here for |
|---|---|---|---|
| **Yahoo Finance** (unofficial) | No published quota; no API key at all | None - nothing to sign up for | Default data source: global search, quotes, candles, day movers. Unofficial/undocumented - can change without notice, which is the real tradeoff for zero setup. |
| **CoinGecko** | ~10–30 req/min on the public tier, no key | None - nothing to sign up for | Crypto quotes (BTC-USD, ETH-USD, etc.) - aggregates across exchanges, generally more accurate for crypto than a single-venue feed. |
| **NSE India** (archives.nseindia.com, unofficial) | A static CSV, no published rate limit, no key | None - nothing to sign up for | The complete, authoritative list of NSE-listed equities (~2,000 symbols) powering `/api/instruments/india` and the TUI's `india` command - more complete for India specifically than Yahoo's general-purpose search. |
| **Finnhub** | 60 calls/min; real-time WebSocket trades for **US-listed symbols only**; company news included free | Free email signup, no card | *Optional*: set `FINNHUB_API_KEY` to get genuine sub-second live ticks (US symbols) on top of the Yahoo-polling baseline, plus the `news` command. Get a key: finnhub.io/register |
| **Alpaca Markets** | Real-time **IEX** feed (one US venue, not the full consolidated tape) via WebSocket, no card needed for data-only/paper use; ~200 req/min REST | Free signup (paper-trading account) | Not wired in. A credible second real-time option if you want to compare against Finnhub, or prefer Alpaca's SDK. alpaca.markets |
| **Twelve Data** | 800 req/day, 8 req/min; ~1-minute-delayed US prices; stocks+forex+crypto+indices in one API | Free email signup | Not wired in. Reasonable fallback if Yahoo's unofficial endpoints ever get rate-limited or blocked for you. twelvedata.com |
| **Alpha Vantage** | 25 req/day - genuinely tight | Free email signup | Not wired in. Mainly useful for its technical-indicator and fundamentals endpoints if you want a second opinion on the server-side math already in `indicators.py`. alphavantage.co |
| **Financial Modeling Prep (FMP)** | 250 req/day | Free signup | Not wired in. Solid for company fundamentals (P/E, balance sheet data) if you want to extend past price/volume. financialmodelingprep.com |
| **Massive** (formerly Polygon.io) | End-of-day only on the free plan (no intraday/real-time), 5 req/min, 2 years of history | Free signup | Not wired in. A licensed (not scraped/unofficial) historical source if you want something with an actual SLA for backtesting. massive.com |
| **NewsAPI.org** | 100 req/day, articles delayed 24h, **free tier is dev/test only - their ToS doesn't allow production use** | Free signup | Not wired in, deliberately: Finnhub's company-news endpoint (already integrated, free tier includes it) is the production-safe choice for the same kind of data. |

## Notes on the ones actually in the code

- **Yahoo + CoinGecko** power everything by default - `backend/app/services/yahoo_client.py` and `coingecko_client.py`. No env var needed.
- **Finnhub** is the only one with an env var: `FINNHUB_API_KEY` in `backend/.env`. Leaving it blank just means you're on polling instead of tick-level push for US symbols - nothing breaks.
- Swapping or adding a provider means touching exactly one file:
  `backend/app/services/market_data.py` is the single place that decides
  which client handles which symbol.

## Things that used to be on lists like this and aren't anymore

- **IEX Cloud** shut down in August 2024 - if you see it recommended in an
  older guide, it's dead.
