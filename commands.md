# Market Terminal - Command Guide (Simple English)

This guide explains the commands and keyboard controls that are present in this project. You can type commands in the input line at the bottom of the terminal. Press `/` from anywhere to move the cursor to that input line.

> **Important:** This is a market-data and research terminal. It does not place live orders with a broker. The project has no live broker order-routing connection. The India-wide screener uses available Yahoo Finance quote snapshots, so prices and coverage can be delayed or incomplete. It is not an exchange-certified live feed.

## 1. Start the application

Open two PowerShell windows.

### Window 1 - Backend

From the project folder:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If this is the first run, create the environment and install the packages first:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Window 2 - Terminal interface

```powershell
cd tui
.\.venv\Scripts\Activate.ps1
$env:MARKET_TERMINAL_API_BASE = "http://127.0.0.1:8000"
$env:MARKET_TERMINAL_WS_BASE = "ws://127.0.0.1:8000"
python main.py
```

For a first run of the TUI, create its environment and install its packages:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The backend must stay running while you use the terminal interface.

## 2. Basic commands

| Command | What it does | Example |
|---|---|---|
| `help` or `?` | Shows a short command hint in the feedback line. | `help` |
| `add SYMBOL` | Adds one or more symbols to your watchlist. | `add RELIANCE.NS TCS.NS` |
| `watch SYMBOL` | Another name for `add`. | `watch INFY.NS` |
| `rm SYMBOL` | Removes one or more symbols from your watchlist. | `rm TCS.NS` |
| `remove SYMBOL` | Another name for `rm`. | `remove INFY.NS` |
| `unwatch SYMBOL` | Another name for `rm`. | `unwatch SBIN.NS` |
| `select SYMBOL` | Opens that stock in the main chart. | `select RELIANCE.NS` |
| `sel SYMBOL` | Another name for `select`. | `sel TCS.NS` |
| `SYMBOL` | Typing a ticker by itself also selects it. | `HDFCBANK.NS` |
| `search QUERY` | Searches for a company or symbol across supported global listings. | `search tata motors` |
| `find QUERY` | Another name for `search`. | `find nvidia` |
| `quit` or `exit` | Closes the terminal application. | `quit` |

### Indian ticker examples

Use the `.NS` suffix for NSE symbols when selecting, adding, or searching by ticker:

```text
RELIANCE.NS
TCS.NS
INFY.NS
HDFCBANK.NS
ICICIBANK.NS
SBIN.NS
LT.NS
ITC.NS
BHARTIARTL.NS
```

These are symbol examples, not investment recommendations.

### Watchlist notes

- Your watchlist is stored locally on this computer in `%USERPROFILE%\.market-terminal\watchlist.json`.
- Adding a stock saves it so it is still in the watchlist after you close and reopen the TUI.
- The TUI watchlist is local JSON storage in this version. Supabase watchlist synchronization is not enabled in the terminal yet.
- The app filters reserved words such as `INDIA-MOVERS` so they cannot be added as ticker symbols.

## 3. Browse and search Indian shares

| Command | What it does |
|---|---|
| `india` | Opens the NSE-listed equity browser. |
| `india QUERY` | Searches the NSE instrument list by symbol or company name. |

Try:

```text
india
india reliance
india hdfc
india tata
india suzlon
india adani
india infosys
```

The NSE instrument list helps find the exchange symbol. It is not a live-price feed by itself. Once you find a symbol, use `select SYMBOL` to open its chart or `add SYMBOL` to watch it.

## 4. Global movers versus Indian movers

These are two different features. They have intentionally different commands.

### Existing global movers

```text
movers gainers
movers losers
movers active
```

- `gainers`: global/US-market stocks with the largest positive moves in the provider's screener.
- `losers`: global/US-market stocks with the largest negative moves.
- `active`: global/US-market stocks with high activity.

The `movers` command is not the India-wide NSE screener.

### India-wide NSE screener

Start a full-screen NSE screener with:

```text
india-movers gainers
```

The following category commands are supported:

| Command | What it displays |
|---|---|
| `india-movers gainers` | NSE shares ranked by percentage gain. |
| `india-movers losers` | NSE shares ranked by percentage loss. |
| `india-movers active` | NSE shares ranked by reported trading volume. |
| `india-movers turnover` | NSE shares ranked by estimated turnover (last price × reported volume). |
| `india-movers unusual-volume` | Shares with unusually high volume compared with available average volume. |
| `india-movers all` | All NSE equities for which the provider returned a quote. |

Aliases are also accepted:

```text
screener gainers
nse losers
india-movers top-gainers
india-movers top-losers
india-movers most-active
india-movers volume-spike
india-movers unusual
```

## 5. Screener filters - narrow down the results

You can add filters after the category. Filters are written as `name=value`.

| Filter | Meaning | Example |
|---|---|---|
| `min_price` | Only show shares at or above this price. | `min_price=50` |
| `max_price` | Only show shares at or below this price. | `max_price=2000` |
| `min_change` or `min_change_pct` | Minimum daily percentage change. | `min_change=2` |
| `max_change` or `max_change_pct` | Maximum daily percentage change. | `max_change=-1` |
| `min_volume` | Minimum reported share volume. | `min_volume=100000` |
| `min_turnover` | Minimum estimated turnover in rupees. | `min_turnover=50000000` |
| `min_turnover_cr` | Minimum estimated turnover in crore rupees. | `min_turnover_cr=5` |
| `min_rvol` or `min_relative_volume` | Minimum relative volume. `2` means about twice the available average volume. | `min_rvol=2` |
| `series` | NSE series filter. Use `EQ` or `ALL`. | `series=EQ` |
| `limit` | Maximum number of results returned. | `limit=100` |
| `offset` | Skip this many results (for paging). | `offset=50` |
| `sort` or `sort_by` | Choose the ranking field. | `sort=turnover` |
| `order` | Sort direction: `asc` or `desc`. | `order=desc` |

Supported sort fields:

```text
change_pct
volume
turnover
relative_volume
ltp
market_cap
symbol
```

### Useful screener examples

**Find shares gaining 2% or more, priced above ₹20, with at least 100,000 shares traded:**

```text
india-movers gainers min_change=2 min_price=20 min_volume=100000
```

**Find shares down 2% or more with at least 50,000 shares traded:**

```text
india-movers losers max_change=-2 min_volume=50000
```

**Find active shares with at least ₹5 crore estimated turnover:**

```text
india-movers active min_turnover_cr=5
```

**Find shares with relative volume of at least 2×:**

```text
india-movers unusual-volume min_rvol=2
```

**Rank by estimated turnover, highest first:**

```text
india-movers turnover sort=turnover order=desc
```

**Ask for up to 100 results from the full series list:**

```text
india-movers all series=ALL limit=100 offset=0
```

**Show a second page of results:**

```text
india-movers gainers limit=50 offset=50
```

Filter thresholds are examples. They are not buy or sell recommendations.

## 6. Controls inside the full-screen India screener

After you run `india-movers ...`, the screener opens as a full-screen table.

| Key | What it does |
|---|---|
| `Up` / `Down` | Move the highlighted row. |
| `PageUp` / `PageDown` | Move up or down by one screen of rows. |
| `Home` / `End` | Jump to the first or last visible row. |
| `Enter` | Select the highlighted stock and open it in the main chart. |
| `D` | Open the detailed stock view. |
| `W` | Add the highlighted stock to your watchlist. |
| `F` | Move the cursor to the filter box. Type a symbol or company name to filter the rows currently displayed. |
| `R` | Request a fresh screener scan. The backend can apply an upstream rescan cooldown. |
| `G` | Switch to gainers. |
| `L` | Switch to losers. |
| `A` | Switch to most active by volume. |
| `T` | Switch to turnover leaders. |
| `U` | Switch to unusual-volume results. |
| `Space` | Pause or resume the 60-second automatic refresh. |
| `Esc` | Close the screener and return to the main terminal. |

The table shows symbol, company, last traded price, percentage change, reported volume, estimated turnover and relative volume. It also displays quote coverage and the scan time.

## 7. Detailed stock view

While the screener is open:

1. Use `Up` / `Down` to highlight a company.
2. Press `D`.
3. Read the quote and market statistics.
4. Review the daily price history chart and technical indicator values.
5. Press `W` to add the company to your watchlist, or `Enter` to open it in the main chart.
6. Press `Esc` to go back.

The detailed view can show available fields such as last traded price, day change, open, previous close, day high/low, 52-week high/low, volume, average volume, relative volume, estimated turnover, market cap, series and ISIN. A field may show `-` if the provider does not supply it.

## 8. Charts and technical indicators

Choose a stock first:

```text
select RELIANCE.NS
```

Then change the chart timeframe:

```text
interval 1m
interval 5m
interval 15m
interval 1h
interval 1d
interval 1w
```

`int` is an alias for `interval`:

```text
int 1d
```

The backend calculates these indicators from the available candle history:

- **SMA 20:** average closing price over 20 candles.
- **EMA 12:** a moving average that reacts more quickly to recent prices.
- **EMA 26:** a longer responsive moving average.
- **RSI 14:** a momentum measure often used to study the strength of recent price moves.

The main chart is a compact terminal chart, not a full broker charting package. Historical candle availability depends on the data provider and selected timeframe.

## 9. News

Select a stock and run:

```text
select RELIANCE.NS
news
```

The news panel requires `FINNHUB_API_KEY` to be configured in the backend `.env` file. Without that key, the news feature may report that it is not configured.

## 10. Main terminal keyboard controls

| Key | What it does |
|---|---|
| `/` | Focus the command input at the bottom. |
| `Up` / `Down` | Navigate the watchlist when it has focus. |
| `Enter` | Select the highlighted watchlist item. |
| `Ctrl+Q` | Quit the application. |

The terminal adapts to smaller windows. At narrow widths, the side panel may hide; at very narrow widths, the watchlist may also hide so the chart remains usable. Resize the terminal window if the layout feels cramped.

## 11. Simple practice session

Try this sequence to learn the main features:

```text
help
india reliance
add RELIANCE.NS TCS.NS INFY.NS HDFCBANK.NS
select RELIANCE.NS
interval 1d
india-movers gainers
```

Inside the screener:

1. Move down a few rows with `Down`.
2. Press `D` to see company details.
3. Press `Esc` to return.
4. Press `W` to add the highlighted stock to the watchlist.
5. Press `R` to refresh.
6. Press `Space` to pause automatic refresh.
7. Press `Esc` to return to the main terminal.

Then try:

```text
india-movers losers
india-movers active
india-movers unusual-volume min_rvol=2
movers gainers
search nvidia
news
```

The last `news` command uses whichever stock is currently selected.

## 12. Check the backend in Swagger UI

When the backend is running, open these local pages in a browser:

- Swagger API tester: `http://127.0.0.1:8000/docs`
- ReDoc reference: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/api/health`
- Provider diagnostics: `http://127.0.0.1:8000/api/health/providers?probe=true`

Useful API requests to try in Swagger's **Try it out** section:

| Endpoint | What to test |
|---|---|
| `GET /api/market/quote/{symbol}` | One quote, for example `RELIANCE.NS`. |
| `GET /api/market/quotes` | Several watchlist quotes; the endpoint accepts up to 50 symbols. |
| `GET /api/market/candles/{symbol}` | OHLC price history. |
| `GET /api/market/indicators/{symbol}` | SMA, EMA and RSI values. |
| `GET /api/market/movers` | Existing global/US movers. |
| `GET /api/market/india/screener` | India-wide NSE screener. |
| `GET /api/instruments/india` | NSE instrument browser/search. |
| `GET /api/instruments/search` | Global instrument search. |

A successful HTTP response does not mean every exchange symbol has a quote. Read the screener's `meta` information, especially quote coverage, failed batches, scan time and data notes.

## 13. Understanding the data and common issues

- The NSE instrument list is used to find listed companies and their symbols. A symbol appearing in that list does not guarantee a live quote is available.
- The screener fetches available quotes from Yahoo Finance in batches. It may return partial coverage if a provider is unavailable, rate-limits requests or does not recognize a symbol.
- The displayed NSE quote snapshot is best-effort data, not an exchange-certified real-time feed.
- Estimated turnover is calculated from reported price × reported volume. It is an estimate, not guaranteed official exchange turnover.
- Relative volume compares the current reported volume with the average-volume field when available. It may be missing for some stocks.
- CoinGecko can rate-limit crypto requests. A crypto provider issue should not be interpreted as an NSE market move.
- HTTP `401` or `429` messages usually indicate a provider authentication or rate-limit problem. Wait, retry later, and inspect `GET /api/health/providers?probe=true`.
- HTTP `404` for a quote or candle means the provider did not return that instrument's data.
- HTTP `422` for `INDIA-MOVERS` is intentional: `INDIA-MOVERS` is a screener label, not a stock ticker. Use `india-movers gainers` in the terminal instead.
- The app uses a local watchlist JSON file. Server-synced Supabase watchlists are not enabled in this terminal build.
- Live broker execution, persistent alert notifications, the economic calendar and multi-level order-book depth are not implemented in this build.

## 14. Quick reference

```text
# Basic watchlist and stock commands
add RELIANCE.NS TCS.NS
rm TCS.NS
select RELIANCE.NS
search tata motors

# NSE instrument browser
india
india reliance

# Global/US movers
movers gainers
movers losers
movers active

# India-wide NSE screeners
india-movers gainers
india-movers losers
india-movers active
india-movers turnover
india-movers unusual-volume
india-movers all

# Filtered screens
india-movers gainers min_change=2 min_price=50 min_volume=100000
india-movers losers max_change=-2 min_rvol=1.5
india-movers unusual-volume min_rvol=2
india-movers turnover sort=turnover order=desc

# Chart, news and help
interval 5m
interval 1d
news
help
quit
```
