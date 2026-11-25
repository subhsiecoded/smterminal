# Market Terminal

A FastAPI market-data backend plus a real terminal application (not a
website) - green-phosphor, command-line-driven, live ticks streaming into
your terminal emulator. Global tickers, no login, no broker account.

```
backend/   FastAPI - the data engine. No external services at all: no Redis, no database required to run it
tui/       Textual TUI client - the actual interactive surface now (replaces the old Next.js app)
supabase/  Schema for login/orders/watchlists - intact but dormant, see "Re-enabling login" below
API_KEYS.md  Every free API key relevant here, what's wired in vs. just an option
```

## This pass: the entire India stock market

Global search (Yahoo's) is good at well-known names but was never
guaranteed complete for India specifically. `backend/app/services/
nse_universe.py` now loads NSE's own published master list of every
listed equity (~2,000 symbols, from `archives.nseindia.com` - no key,
no login, same zero-config posture as Yahoo/CoinGecko) and serves it via
`GET /api/instruments/india`: browse the whole exchange paginated, or
search it by symbol/company name, with every result's `yahoo_symbol`
(e.g. `RELIANCE.NS`) ready to hand straight to the existing quote/candle/
indicator endpoints. The TUI's new `india` / `india QUERY` commands use
exactly this. The default watchlist now leads with India
(`RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`, the Nifty 50 and
Nifty Bank indices) with a couple of global names kept alongside to show
the rest of the world is still one `select` away.

Verified end-to-end over real HTTP (NSE's own servers aren't reachable
from this sandbox, so the universe was seeded with synthetic rows
matching NSE's real column layout to test the actual logic - pagination,
symbol-prefix-first search ranking, series filtering, and the graceful
503 when NSE itself is down): see `backend/app/services/nse_universe.py`'s
own self-check for the parsing logic specifically, run against NSE's
documented CSV columns including the stray header whitespace that's
been observed in the wild.

## This pass: "no website" and "more advanced"

The web frontend is gone - deleted, not just unlinked - replaced with
`tui/`, a genuine terminal application built on
[Textual](https://textual.textualize.io/). See `tui/README.md` for
commands and keybindings. The backend gained real features to back it:

- **Technical indicators**, computed server-side from real candle
  history: SMA(20), EMA(12/26), RSI(14), using Wilder's actual smoothing
  formula (`backend/app/services/indicators.py`) - verified against his
  own textbook worked example, not just "looks about right."
- **Day movers** - gainers/losers/most-active - via Yahoo's (undocumented,
  best-effort-parsed) screener endpoint.
- **Crypto quotes now route through CoinGecko** instead of Yahoo
  (`backend/app/services/market_data.py`), which needs no API key at all
  and aggregates across exchanges - more representative than a single
  venue for something as fragmented as crypto pricing.
- **Company news**, if you set `FINNHUB_API_KEY` - free, included on
  their free tier, distinguishes "not configured" from "no news found"
  rather than showing an ambiguous empty panel either way.
- See **`API_KEYS.md`** for the full picture: every free provider
  relevant to this app, what's actually wired in, and what's just a
  credible alternative if you want it.

## No Redis - dropped entirely, not relocated

An earlier pass added Redis for caching and pub/sub, with a comment that
it'd let the app scale across multiple processes someday. It never
actually needed to for this deployment - everything (the poller, the
optional Finnhub overlay, the WS gateway, every HTTP route) runs in one
Python process - so Redis was pure setup friction for zero present
benefit. It's gone:

- **`app/services/memory_store.py`** - a plain in-process dict with
  per-key TTLs, replacing Redis for quote/candle/movers caching.
- **`app/services/pubsub.py`** - in-process publish/subscribe (each WS
  connection owns one `asyncio.Queue`), replacing Redis pub/sub for
  fanning ticks out to connected clients.
- Rate limiting now uses slowapi's in-memory storage instead of a
  Redis-backed one.

**The whole backend now runs with zero external services** - `pip
install -r requirements.txt && uvicorn app.main:app` and that's it. No
Redis, no Postgres, no Docker, nothing to have running in another window.
(This does mean it's single-process only now - fine for personal use;
if you ever actually need multiple backend replicas, that's the one
place Redis would need to come back, and `rate_limit.py`'s and
`memory_store.py`'s own comments say so.)

Proven, not just asserted: the app was imported and fully exercised -
every route, the WS gateway, rate limiting - with the `redis` Python
package **uninstalled from the environment entirely**, so there's no
way a leftover import could be silently making this still secretly
depend on it.

## Verified, not just written - this pass specifically

- **A real connection-handling bug** (caught earlier, when Redis was
  still in the picture): `relay_ticks` called `pubsub.get_message()`
  before any `subscribe()` had happened, which redis-py treats as an
  error, silently killing every connection. Fixed and re-verified then;
  moot now that the WS gateway's fanout is in-process instead.
- **A test-harness artifact caught and rejected, not trusted**: verifying
  the new in-process pub/sub with Starlette's `TestClient` produced an
  indefinite hang on the second publish/receive round-trip. Rather than
  explain it away, the test was redone against a real `uvicorn.Server`
  and a real `websockets` socket connection in the same process - which
  passed cleanly, including the specific case that matters most
  (a symbol correctly stops receiving ticks after `unsubscribe`). The
  hang was a quirk of the synchronous test client's bridging, not a bug
  in the app; the fix was to stop trusting that harness for this, not to
  paper over the symptom.
- **Real interop between the TUI and the backend** - not just each side's
  own mocked tests. `tui/app/tickstream.py` was pointed at an actually
  running backend and subscribed over a real WebSocket.
- **A feedback-overwriting bug** in the TUI's command dispatch: selecting
  a bad symbol would show a clear `[chart] No candle data found` error,
  and then the `select` command's own success message would immediately
  stomp over it with a false "→ SYMBOL". Fixed by having the refresh
  function report success/failure instead of assuming it.
- **A Rich-markup bug that silently ate every bracketed status prefix**:
  `[chart]`, `[search]`, etc. in command feedback were being parsed as
  (invalid, silently-dropped) Rich markup tags by `Static.update(str)`,
  so the prefix just vanished with zero error - caught by actually reading
  the rendered text in a test, not just checking a call didn't throw.
  Fixed at the source (wrap feedback in a `Text()` object) rather than
  by renaming the prefixes, so any future message with brackets in it -
  including a raw API error string - is safe too.
- **A responsive-layout bug**: at a narrow terminal width, the two
  fixed-width side panels left the chart at 0 columns. Caught by actually
  resizing the app under test, not just eyeballing one window size. Fixed
  with a two-stage breakpoint that drops the side panel, then the
  watchlist, before the chart is allowed to collapse.
- The indicators module's own self-check initially asserted the wrong
  reference point against Wilder's textbook example (right formula,
  wrong row of his worked table) - caught immediately on first run,
  before it could become "a test that passes but proves the wrong thing."

## Running it locally

No external services - just two Python environments.

```bash
# 1. Backend - works with just one required var
cd backend
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # → APP_SECRET_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload
# optional: FINNHUB_API_KEY in .env for real-time US ticks + news - see API_KEYS.md

# 2. TUI - in another terminal
cd ../tui
pip install -r requirements.txt
python main.py
```

## What's still stubbed, on purpose

- Live order routing to any broker - there isn't one; everything is
  paper-trading only, by design.
- Persistent alert evaluation/notifications and the economic calendar are
  still roadmap items. The NSE-wide quote screener is implemented below;
  the existing `movers` command remains the global/US Yahoo screener.
- Depth-of-market beyond top-of-book - no free feed actually provides
  real multi-level depth; `side_panel.py` says so rather than faking it.

## Re-enabling login

Orders and server-synced watchlists are still behind Supabase auth - the
code's intact, just dormant, from before the web frontend existed. With
no frontend anymore, re-enabling it means wiring the TUI to carry a
bearer token (`tui/app/client.py` would need an `Authorization` header)
rather than restoring `/login` - there's no browser session to put it in.

## Next steps, in roadmap order

1. If you want trading/persistence back: wire TUI auth (above), or build
   a new frontend against the still-intact `/api/orders`/`/api/watchlists`.
2. Add persistent alert evaluation/notifications and an economic-calendar
   router - the database schema is ready.
3. Real multi-level depth, if you ever add a licensed data source that
   actually provides it (see `API_KEYS.md` - none of the free ones do).
4. A matrix-rain decorative flourish in the TUI, if you want the look
   pushed further - the banner/theme/ticker-tape carry the aesthetic now,
   deliberately kept simple so the data panels stayed the priority.


## NSE-wide India market screener (added)

The backend now exposes `GET /api/market/india/screener`, which scans the NSE equity master list (EQ series by default), fetches Yahoo Finance quote snapshots in bounded batches, computes indicative turnover and relative volume, and ranks gainers, losers, active stocks, turnover leaders, and unusual-volume candidates. The response includes quote coverage, failed batch count, scan timestamp, provider, and data-quality notes. Results are cached for 60 seconds.

Example requests:

```text
GET /api/market/india/screener?category=gainers&limit=50
GET /api/market/india/screener?category=losers&min_change_pct=-2&max_change_pct=-0.5
GET /api/market/india/screener?category=active&min_volume=100000
GET /api/market/india/screener?category=unusual-volume&min_relative_volume=1.5
GET /api/market/india/screener?category=turnover&sort_by=turnover&order=desc
```

The terminal adds the `india-movers` / `screener` command and a full-screen cursor-driven results table. `movers gainers|losers|active` remains unchanged. The screener is best-effort because Yahoo's quote endpoint is unofficial; it is not an exchange-certified real-time feed.
