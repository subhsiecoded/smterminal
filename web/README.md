# SM Terminal Web (JavaScript)

A browser-native Next.js implementation of the Python Textual terminal. This
app is written in **JavaScript and JSX only**—there are no TypeScript source
files, TypeScript compiler dependency, `tsconfig.json`, or `next-env.d.ts`.
It uses the same FastAPI backend and recreates the TUI's green-phosphor
visual language, block-character chart, watchlist, live ticker, command bar,
side panel, and NSE screener.

## Requirements

- Node.js 22 or newer
- npm
- Python 3.10+ for the FastAPI backend

## Run locally

### 1. Configure and start the backend

From the repository root:

```bash
cd backend
cp .env.example .env
python -m pip install -r requirements.txt
python -c "import secrets; print(secrets.token_hex(32))"
```

Put the generated value in `APP_SECRET_KEY` in `backend/.env`, then run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`FINNHUB_API_KEY` is optional. Without it the backend uses Yahoo Finance
polling; the website still works. The Supabase and PostgreSQL variables are
not needed for market-data-only use. The related orders and server-synced
watchlists remain dormant until Supabase auth is configured.

**Supabase URL distinction:** `SUPABASE_URL` must be the HTTPS project API
URL (`https://<project-ref>.supabase.co`) because `supabase-py` passes it to
`create_client`. `DATABASE_URL` is the PostgreSQL connection string used by
`asyncpg`. Do not put a `postgresql://` DSN in `SUPABASE_URL`. Replace
`YOUR_DB_PASSWORD` in `DATABASE_URL` with the database password; URL-encode
reserved characters in that password.

### 2. Configure and start the JavaScript website

Open a second terminal from the repository root:

```bash
cd web
cp .env.example .env.local
```

Set these values in `web/.env.local`:

- `TERMINAL_ACCESS_PASSWORD`: the shared password you will give website users.
- `TERMINAL_SESSION_SECRET`: a random secret of at least 32 characters.
- `MARKET_TERMINAL_API_BASE_URL`: leave as `http://127.0.0.1:8000` for local development.
- `MARKET_TERMINAL_WS_BASE_URL`: leave as `ws://127.0.0.1:8000` for local development.

Generate secrets with:

```bash
node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"
```

Then install dependencies and start Next.js:

```bash
npm install
npm run dev
```

Open `http://localhost:3000` and sign in using `TERMINAL_ACCESS_PASSWORD`.
On Windows PowerShell, use `Copy-Item .env.example .env` in `backend`, and
`Copy-Item .env.example .env.local` in `web`.

### 3. Run the Python TUI as well (optional)

In another terminal, from the repository root:

```bash
cd tui
python -m pip install -r requirements.txt
python main.py
```

The browser app and TUI use the same backend, but their watchlists are
separate: the browser saves its watchlist in that browser's local storage.

## Docker Compose

Create `backend/.env` and `web/.env.local` as described above, then run from
the repository root:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The backend port is exposed on `localhost:8000`
for the browser's live WebSocket connection.

## Commands

The browser command bar supports the TUI command vocabulary:

| Command | Effect |
|---|---|
| `AAPL` / `select AAPL` | Select a ticker and load its chart |
| `add AAPL` / `watch AAPL` | Add to the browser-local watchlist |
| `rm AAPL` / `unwatch AAPL` | Remove a symbol from the watchlist |
| `search tesla` | Search global instruments |
| `india` / `india reliance` | Browse or search NSE equities |
| `movers gainers` / `losers` / `active` | Global/US movers in the side panel |
| `india-movers gainers` | Full-screen NSE screener; also `losers`, `active`, `turnover`, `unusual-volume`, `all` |
| `news` | News for the selected symbol (requires backend `FINNHUB_API_KEY`) |
| `interval 1m` | Set chart interval; valid values: `1m`, `5m`, `15m`, `1h`, `1d`, `1w` |
| `help` | Show command reference |

The screener includes client-side symbol/company filtering, category
switching, manual refresh, and a 60-second auto-refresh toggle.

## Production deployment and shared credentials

Deploy the FastAPI backend and Next.js app as separate services. Keep all
secrets in server-side environment settings; do not put them in browser code
or variables prefixed with `NEXT_PUBLIC_`.

**Backend environment** (`backend/.env` or your backend host's secret store):

```dotenv
APP_SECRET_KEY=<unique-random-secret>
FINNHUB_API_KEY=<optional-provider-key>
FRONTEND_ORIGIN=https://smterminal-web.vercel.app
ENVIRONMENT=production
TERMINAL_BACKEND_TOKEN=<random-shared-backend-token>
TERMINAL_WS_SECRET=<random-shared-websocket-secret>
```

`FRONTEND_ORIGIN` must match the browser's address bar exactly (scheme and
host, no path). Add additional production or preview origins as a
comma-separated list only when you intentionally use them. The WebSocket
checks this value before accepting a connection; leaving it at
`http://localhost:3000` causes the exact `1008 origin_mismatch` failure shown
in the browser console.

**Next.js environment** (`web/.env.local` locally, or your web host's server
secret store):

```dotenv
MARKET_TERMINAL_API_BASE_URL=https://your-backend.example.com
MARKET_TERMINAL_WS_BASE_URL=wss://your-backend.example.com
TERMINAL_ACCESS_PASSWORD=<long-unique-shared-website-password>
TERMINAL_SESSION_SECRET=<independent-random-session-secret>
TERMINAL_BACKEND_TOKEN=<same-value-as-backend>
TERMINAL_WS_SECRET=<same-value-as-backend>
```

`MARKET_TERMINAL_API_BASE_URL` and `MARKET_TERMINAL_WS_BASE_URL` must point
to the deployed backend; the second URL must be publicly reachable over WSS.
`TERMINAL_BACKEND_TOKEN` and `TERMINAL_WS_SECRET` must match between the
backend and Next.js server. The website server adds the private backend
header and issues short-lived WebSocket tickets after verifying a signed,
HttpOnly website session. In production the backend rejects market-data API
requests without the server token, and the WebSocket requires a ticket.
`APP_SECRET_KEY` must also be unique in production.

The website uses one shared access password, not individual user accounts.
Everyone who has it shares the backend provider quota. Give visitors only
the website URL and access password—never the `.env` file, Finnhub key,
backend token, session secret, or WebSocket secret. Rotate the shared
password when you want to revoke access. Use HTTPS/WSS and hosting-provider
rate limiting for public deployments.

For local development, leave `TERMINAL_BACKEND_TOKEN` and
`TERMINAL_WS_SECRET` blank in both services. The standalone Python TUI can
continue to connect directly to the local backend in this mode.

## Boundaries

- This is a browser-native recreation of the TUI, not Textual running inside
a browser. Both clients share the FastAPI APIs; browser layout adapts to the
window size.
- The website is read-only. No broker is connected and the website does not
expose the dormant order endpoints.
- Yahoo Finance/NSE snapshots are best-effort and are not exchange-certified
real-time data. Finnhub's optional streaming overlay applies to US-listed
symbols. See `../api_keys.md` for provider limitations.
