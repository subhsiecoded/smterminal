# Market Terminal

A FastAPI market-data engine with two green-phosphor clients: a keyboard-first
Python Textual TUI and a Next.js website. Both clients use the same quote,
candle, indicator, screener and live-tick APIs. Global tickers; no broker
account is required for market research.

```
backend/   FastAPI market-data engine; no database required for market data
tui/       Python Textual terminal for a local terminal emulator
web/       Next.js browser terminal (JavaScript/JSX only; no TypeScript)
api_keys.md  Provider keys: what's wired in, what's optional, and what's not used
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

## Terminal clients: TUI and web

The Python TUI remains the native terminal-emulator experience. `web/` now
provides a browser-native companion built with Next.js and plain JavaScript/JSX
(no TypeScript source or compiler dependency); it recreates the TUI's
green-phosphor layout, block-character price chart, watchlist, ticker
tape, side panel, command bar and NSE screener. It calls the same FastAPI
endpoints rather than reimplementing market-data calculations. See
`web/README.md` for the web setup and deployment details.

The backend's market features include:

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
- See **`api_keys.md`** for the full picture: every free provider
  relevant to this app, what's actually wired in, and what's just a
  credible alternative if you want it.



## Verified, not just written - this pass specifically

- **A real connection-handling bug** : `relay_ticks` called `pubsub.get_message()`
  before any `subscribe()` had happened, , silently killing every connection. Fixed and re-verified then;
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

Clone the repository and open three terminal windows. The backend is shared
by both clients; you can run the Python TUI, the Next.js website, or both.
Yahoo Finance and CoinGecko need no API key. `FINNHUB_API_KEY` is optional.

### 1. Start the backend

In terminal 1, from the repository root:

```bash
cd backend
cp .env.example .env
python -m pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `APP_SECRET_KEY` in `backend/.env`, then run:

```bash
uvicorn app.main:app --reload
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

### 2. Start the Next.js website

In terminal 2, from the repository root:

```bash
cd web
cp .env.example .env.local
```

Edit `web/.env.local`: set `TERMINAL_ACCESS_PASSWORD` to the shared
website sign-in password and set `TERMINAL_SESSION_SECRET` to an independent
random value. For example:

```bash
node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"
```

Then start the web app:

```bash
npm install
npm run dev
```

On Windows PowerShell, use `Copy-Item .env.example .env.local` instead of
`cp`. Open `http://localhost:3000` and sign in with
`TERMINAL_ACCESS_PASSWORD`.

### 3. (Optional) Start the Python TUI

In terminal 3, from the repository root:

```bash
cd tui
python -m pip install -r requirements.txt
python main.py
```

### Docker Compose

After creating `backend/.env` and `web/.env.local` as above, run this from
the repository root:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The WebSocket endpoint is exposed separately
on `localhost:8000` for the browser's live feed.

## Environment template notes

`backend/.env.example` includes the market-data settings, optional Finnhub
key, and the optional Supabase/PostgreSQL settings for the dormant auth and
order features. `SUPABASE_URL` is the HTTPS Supabase project API URL used by
`supabase-py`; `DATABASE_URL` is the PostgreSQL connection string used by
`asyncpg`. They are different values. Market quotes, candles, search,
screeners, and live ticks do not require Supabase or PostgreSQL. Replace the
`YOUR_DB_PASSWORD` placeholder only if you re-enable database-backed
features.

The web app is JavaScript-only: its pages and components use `.jsx`, server
handlers and helpers use `.js`, and its path alias is configured in
`web/jsconfig.json`. There is no `tsconfig.json`, `next-env.d.ts`, or
TypeScript package in the web project.

## What's still stubbed, on purpose

- Live order routing to any broker - there isn't one; everything is
  paper-trading only, by design.
- Persistent alert evaluation/notifications and the economic calendar are
  still roadmap items. The NSE-wide quote screener is implemented below;
  the existing `movers` command remains the global/US Yahoo screener.
- Depth-of-market beyond top-of-book - no free feed actually provides
  real multi-level depth; `side_panel.py` says so rather than faking it.

## Supabase features remain dormant

Orders and server-synced watchlists still require Supabase user JWTs and
row-level security. The Next.js access password described below protects
the read-only market terminal; it does not create a Supabase user session
or enable the dormant order/watchlist routers. The website's watchlist is
local to each browser.

## Web deployment and credentials

The website is read-only and uses a shared access password. The password is
checked on the Next.js server; authenticated browser sessions are held in a
signed, HttpOnly cookie. Browser requests go through a Next.js server route
that allowlists the market-data endpoints. In production, configure
`TERMINAL_BACKEND_TOKEN` and `TERMINAL_WS_SECRET` in **both** the backend
and Next.js hosting environments with matching random values. The backend
also requires a unique `APP_SECRET_KEY` in production (the development
fallback is rejected). The backend then rejects direct market API requests
without the server token, and the WebSocket accepts only short-lived tickets
signed by the Next.js server.

Keep `FINNHUB_API_KEY` in `backend/.env` or the backend host's secret manager.
Keep `TERMINAL_ACCESS_PASSWORD`, `TERMINAL_SESSION_SECRET`,
`TERMINAL_BACKEND_TOKEN`, and `TERMINAL_WS_SECRET` in the Next.js host's
server-side environment settings. Never use a `NEXT_PUBLIC_` prefix for
these values, never put them in client code, and never commit `.env` files.
Yahoo Finance and CoinGecko need no key; Finnhub is optional. Anyone with
the shared website password uses the same backend provider quota. This is
how you can let people use the hosted terminal with your backend's optional
Finnhub key without giving them the `.env` file. Give them the website URL
and the access password only; never distribute `FINNHUB_API_KEY`, the
backend token, or the session/WebSocket secrets.

A person who clones the repository to run the Python TUI locally starts
their own backend and uses their own optional provider key. Yahoo Finance
and CoinGecko work without a key. The TUI is not configured to connect to
the password-gated hosted backend as a remote multi-user client.

The web watchlist is saved in that user's browser and is not synced to the
local TUI or to other users.

For local development, leave the two backend gate values empty in both
`.env` files; the protected proxy still requires the website password, but
the local API remains available to the standalone TUI. For production, set
matching non-empty values on both servers and restrict backend network
ingress to the Next.js host where your hosting provider allows it.

There is no broker connection in this repository. Orders are login-gated
behind dormant Supabase configuration and live broker routing is not
implemented; the website does not expose an order-entry workflow.

## Next steps, in roadmap order

1. If you want trading/persistence back: wire TUI auth or the Next.js
   frontend against the still-intact `/api/orders`/`/api/watchlists` only
   after restoring proper user auth and connecting a supported broker.
2. Add persistent alert evaluation/notifications and an economic-calendar
   router - the database schema is ready.
3. Real multi-level depth, if you ever add a licensed data source that
   actually provides it (see `api_keys.md` - none of the free ones do).
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
