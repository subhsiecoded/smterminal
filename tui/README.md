# Market Terminal - TUI

A real terminal application (not a website) for the Market Terminal
backend: green-phosphor, keyboard-and-command-line driven, live ticks
streaming straight into your terminal emulator.

## Run it

```bash
cd tui
pip install -r requirements.txt

# Point it at your backend (defaults shown)
export MARKET_TERMINAL_API_BASE=http://localhost:8000
export MARKET_TERMINAL_WS_BASE=ws://localhost:8000

python main.py
```

Needs the backend (`../backend`) running - see the top-level README for
that half. No login, no API keys of your own required to get it running:
the backend's default Yahoo-polling data source needs none.

## Commands

Type into the bar at the bottom (press `/` to focus it from anywhere), or
just type a bare ticker and hit enter to jump straight to it:

| Command | Effect |
|---|---|
| `AAPL` (no verb) | Select AAPL - same as `select AAPL` |
| `add AAPL` / `watch AAPL` | Add to the watchlist (persisted locally) |
| `rm AAPL` / `unwatch AAPL` | Remove from the watchlist |
| `select TSLA` / `sel TSLA` | Show TSLA in the chart + top-of-book |
| `search tesla` | Look up a ticker by name across any global exchange |
| `india` | Browse the complete NSE equity list (~2,000 symbols, NSE's own published data) |
| `india reliance` | Search that same complete NSE list by symbol or company name |
| `movers gainers` \| `losers` \| `active` | Side panel shows the existing global/US day movers (unchanged) |
| `india-movers gainers` | Full-screen NSE-wide gainers screener |
| `india-movers losers` | Full-screen NSE-wide losers screener |
| `india-movers active` | Rank NSE equities by reported volume |
| `india-movers turnover` | Rank by indicative price × reported volume turnover |
| `india-movers unusual-volume` | Relative-volume screen (defaults to ≥1.5× available average volume) |
| `india-movers all` | All NSE equities with a quote returned by the provider |
| `news` | Side panel shows recent headlines for the selected symbol (needs `FINNHUB_API_KEY` on the backend) |
| `interval 5m` | Change the chart's resolution (`1m 5m 15m 1h 1d 1w`) |
| `help` / `?` | Show this list in the feedback line |
| `quit` / `exit` | Quit |

The side panel always comes back to top-of-book the next time you select a
symbol or a new tick arrives for it - `movers`/`news` are one-off views,
not a mode you get stuck in.

## India-wide screener and controls

The India screener scans the NSE equity master list, retrieves available Yahoo Finance quote snapshots in bounded batches, joins the results to NSE company identity, then ranks and filters them. It is cached for 60 seconds and reports quote coverage and failed batches instead of pretending every NSE symbol always has a usable quote.

Examples (filters are optional):

```text
india-movers gainers min_change=2 min_price=20 min_volume=100000
india-movers losers max_change=-2 min_volume=50000
india-movers active min_turnover_cr=5
india-movers turnover sort=turnover order=desc
india-movers unusual-volume min_rvol=2
india-movers all series=ALL limit=100 offset=0
```

Supported filters: `min_price`, `max_price`, `min_change` / `min_change_pct`, `max_change` / `max_change_pct`, `min_volume`, `min_turnover` (INR), `min_turnover_cr` (crore INR), `min_rvol` / `min_relative_volume`, `series=EQ|ALL`, `limit`, `offset`, `sort=change_pct|volume|turnover|relative_volume|ltp|market_cap|symbol`, and `order=asc|desc`.

In the screener window:

- `↑` / `↓` - move the row cursor; `PageUp` / `PageDown` - move by a page; `Home` / `End` - first/last row.
- `Enter` - select the stock and load it in the main chart.
- `D` - open the detailed quote, daily price chart, and SMA/EMA/RSI panel.
- `W` - add the highlighted stock to the local watchlist.
- `F` - focus the live row filter (symbol/company name).
- `G` / `L` / `A` / `T` / `U` - switch to gainers / losers / active / turnover / unusual-volume.
- `R` - request a fresh scan (upstream rescans have a 20-second cooldown); `Space` - pause/resume 60-second auto-refresh; `Esc` - close.

## Keybindings

- `/` - focus the command bar
- `↑`/`↓` + `enter` on the watchlist - select that row's symbol
- `ctrl+q` - quit

## The entire India stock market, specifically

`india` doesn't search a subset or a sample - it's backed by NSE's own
published list of every listed equity
(`backend/app/services/nse_universe.py`), fetched once and cached for 24h.
That's different from `search`, which goes through Yahoo's fuzzy
cross-exchange search and is good at well-known names but isn't
guaranteed complete for India's long tail of small-caps. Every result's
`yahoo_symbol` (e.g. `RELIANCE.NS`) works directly with `select`,
`add`, the chart, and indicators - same data path as everything else,
just a more authoritative way to find the symbol in the first place.

## What's genuinely real vs. honestly approximate

- **Live ticks**: the existing WebSocket watchlist feed is unchanged. The NSE screener separately refreshes its full-market snapshot every 60 seconds; with the current Yahoo provider this is best-effort quote data, not an exchange-certified real-time NSE feed.
- **Top-of-book**: shows real bid/ask when the feed has it, says plainly
  when it doesn't. Never a fabricated depth ladder.
- **Chart**: an ASCII/block-character rendering (`app/ascii_chart.py`) of
  real OHLCV closes - sized to whatever your terminal pane actually is,
  not a fixed grid. It's a bar-style sub-cell-resolution chart, not a true
  connected line plot; readable, not photorealistic.
- **Indicators**: SMA(20)/EMA(12)/EMA(26)/RSI(14) computed server-side
  from real candle data with a standard (Wilder's) formula - see
  `backend/app/services/indicators.py`.

## Terminal size

Below ~95 columns the side panel (top-of-book/movers/news) hides to leave
the chart usable; below ~60 columns the watchlist hides too, leaving just
the chart. Resize your terminal rather than fighting a cramped layout.

## Data quality and operating notes

The full-market scanner uses the NSE-published equity list for instrument coverage and Yahoo Finance's unofficial quote endpoint for price/volume fields. Quote coverage can be partial, and Yahoo may omit or delay some instruments. The table shows coverage and scan time. Turnover is estimated as reported last price multiplied by reported volume; relative volume uses Yahoo's 10-day average volume, falling back to its 3-month average when available. These metrics are screening aids, not guaranteed exchange turnover or trade signals.

The scanner is intentionally separate from the existing `movers` command, existing stock selection/chart flow, watchlist JSON storage, and live tick subscription logic. No existing command was removed.
