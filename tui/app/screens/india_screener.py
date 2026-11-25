import asyncio
from datetime import datetime, timezone

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from ..ascii_chart import render_chart
from ..client import ApiClient, ApiError


_CATEGORY_LABELS = {
    "gainers": "TOP GAINERS",
    "losers": "TOP LOSERS",
    "active": "MOST ACTIVE · VOLUME",
    "turnover": "HIGHEST TURNOVER",
    "unusual-volume": "UNUSUAL VOLUME",
    "all": "ALL QUOTED NSE EQUITIES",
}


def _number(value, decimals=2, fallback="-") -> str:
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return fallback


def _compact(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    for unit, divisor in (("Cr", 10_000_000), ("L", 100_000), ("K", 1_000)):
        if abs(number) >= divisor:
            return f"{number / divisor:,.2f}{unit}"
    return f"{number:,.0f}"


class IndiaScreenerScreen(ModalScreen):
    """Full-screen, keyboard-first NSE screener with auto-refresh and detail drilldown."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "open_selected", "Open chart"),
        Binding("d", "details", "Details"),
        Binding("w", "add_selected", "Add to watchlist"),
        Binding("r", "refresh", "Refresh"),
        Binding("g", "gainers", "Gainers"),
        Binding("l", "losers", "Losers"),
        Binding("a", "active", "Active"),
        Binding("t", "turnover", "Turnover"),
        Binding("u", "unusual", "Unusual vol"),
        Binding("space", "toggle_live", "Pause/live"),
        Binding("f", "focus_filter", "Filter"),
        Binding("home", "first_row", "First row", show=False),
        Binding("end", "last_row", "Last row", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
    ]

    class SymbolSelected(Message):
        def __init__(self, symbol: str):
            self.symbol = symbol
            super().__init__()

    class AddToWatchlist(Message):
        def __init__(self, symbol: str):
            self.symbol = symbol
            super().__init__()

    def __init__(self, api: ApiClient, payload: dict, category: str, params: dict | None = None):
        super().__init__()
        self.api = api
        self.payload = payload
        self.category = category
        self.params = dict(params or {})
        self.rows: list[dict] = []
        self.visible_rows: list[dict] = []
        self._table_key_to_row: dict[str, dict] = {}
        self.live_enabled = True
        self._filter_text = ""
        self._refreshing = False

    def compose(self) -> ComposeResult:
        with Vertical(id="screener-window"):
            yield Static("NSE MARKET SCREENER", id="screener-title")
            yield Static("", id="screener-meta")
            yield Input(placeholder="Filter visible results by symbol or company · press f to focus", id="screener-filter")
            yield DataTable(id="screener-table", cursor_type="row", zebra_stripes=True)
            yield Static("", id="screener-status")
            yield Static(
                "↑/↓ move · PgUp/PgDn page · Home/End jump · Enter chart · D details · W watch · R refresh · G/L/A/T/U screens · Space pause · Esc close",
                id="screener-help",
            )

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("#", key="rank", width=5)
        table.add_column("SYMBOL", key="symbol", width=16)
        table.add_column("COMPANY", key="name", width=34)
        table.add_column("LTP ₹", key="ltp", width=12)
        table.add_column("CHG %", key="change", width=10)
        table.add_column("VOLUME", key="volume", width=12)
        table.add_column("TURNOVER ₹", key="turnover", width=13)
        table.add_column("RVOL", key="rvol", width=8)
        self.set_payload(self.payload)
        table.focus()
        self.set_interval(60, self._auto_refresh)

    def set_payload(self, payload: dict) -> None:
        self.payload = payload
        self.rows = payload.get("results", [])
        self._render_table()
        meta = payload.get("meta", {})
        scanned_at = meta.get("scanned_at")
        scan_label = datetime.fromtimestamp(scanned_at, tz=timezone.utc).astimezone().strftime("%H:%M:%S") if scanned_at else "-"
        coverage = f"{meta.get('quote_count', 0)}/{meta.get('universe_total', 0)} symbols · {meta.get('coverage_pct', 0)}% quote coverage"
        self.query_one("#screener-title", Static).update(
            Text(f"INDIA / NSE  ·  {_CATEGORY_LABELS.get(self.category, self.category.upper())}", style="bold #00ff41")
        )
        meta_text = Text()
        meta_text.append(f"{coverage}   ", style="#00b030")
        meta_text.append(f"SCAN {scan_label}   ", style="#00b030")
        meta_text.append(f"ADV {meta.get('advancers', 0)} / DEC {meta.get('decliners', 0)} / FLAT {meta.get('unchanged', 0)}   ", style="#00b030")
        meta_text.append(f"SERIES {meta.get('series', 'EQ')}   ", style="#00b030")
        meta_text.append(f"CACHE {meta.get('cache_ttl_seconds', 60)}s   ", style="#006622")
        meta_text.append("YAHOO SNAPSHOT · NOT EXCHANGE-CERTIFIED LIVE DATA", style="#c18b35")
        self.query_one("#screener-meta", Static).update(meta_text)
        warning = ""
        if meta.get("failed_batches"):
            warning = f" · {meta['failed_batches']} quote batches failed"
        live_text = "AUTO-REFRESH ON · 60s" if self.live_enabled else "AUTO-REFRESH PAUSED"
        self.query_one("#screener-status", Static).update(
            Text(f"{len(self.visible_rows)} displayed / {payload.get('total', 0)} matches{warning}  ·  {live_text}", style="#00b030")
        )

    def _render_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=False)
        query = self._filter_text.casefold().strip()
        self.visible_rows = [
            row for row in self.rows
            if not query or query in str(row.get("symbol", "")).casefold() or query in str(row.get("name", "")).casefold()
        ]
        self._table_key_to_row = {}
        for index, item in enumerate(self.visible_rows, start=1):
            change = float(item.get("change_pct") or 0)
            change_cell = Text(f"{change:+.2f}%", style="#00ff41" if change >= 0 else "#ff4b4b")
            symbol_cell = Text(item.get("nse_symbol") or item.get("symbol", ""), style="bold #00ff41")
            row_key = f"{item.get('symbol', index)}::{item.get('series') or 'NA'}::{index}"
            self._table_key_to_row[row_key] = item
            table.add_row(
                str(index),
                symbol_cell,
                Text(str(item.get("name", ""))[:33], style="#00b030"),
                _number(item.get("ltp")),
                change_cell,
                _compact(item.get("volume")),
                _compact(item.get("turnover")),
                _number(item.get("relative_volume"), 2),
                key=row_key,
            )
        if self.visible_rows:
            table.move_cursor(row=0, column=0)
        self.query_one("#screener-status", Static).update(
            Text(f"{len(self.visible_rows)} displayed / {self.payload.get('total', 0)} matches", style="#00b030")
        )

    def _selected(self) -> dict | None:
        if not self.visible_rows:
            return None
        row_index = max(0, min(self.query_one(DataTable).cursor_coordinate.row, len(self.visible_rows) - 1))
        return self.visible_rows[row_index]

    async def refresh_data(self, force: bool = True, silent: bool = False) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        if not silent:
            self.query_one("#screener-status", Static).update(Text("Scanning NSE universe…", style="#c18b35"))
        try:
            params = {**self.params, "category": self.category, "refresh": force}
            payload = await self.api.get_india_screener(**params)
            self.set_payload(payload)
            if not silent:
                self.query_one("#screener-status", Static).update(Text("NSE snapshot updated", style="#00ff41"))
        except ApiError as exc:
            self.query_one("#screener-status", Static).update(Text(f"Screener refresh failed: {exc}", style="#ff4b4b"))
        finally:
            self._refreshing = False

    def _auto_refresh(self) -> None:
        if self.live_enabled and not self._refreshing:
            asyncio.create_task(self.refresh_data(force=True, silent=True))

    def action_close(self) -> None:
        self.dismiss()

    def action_open_selected(self) -> None:
        item = self._selected()
        if item:
            self.post_message(self.SymbolSelected(item["symbol"]))
            self.dismiss()

    def action_details(self) -> None:
        item = self._selected()
        if item:
            self.app.push_screen(IndiaStockDetailScreen(self.api, item))

    def action_add_selected(self) -> None:
        item = self._selected()
        if item:
            self.post_message(self.AddToWatchlist(item["symbol"]))
            self.query_one("#screener-status", Static).update(Text(f"Added request: {item['symbol']}", style="#00ff41"))

    def action_refresh(self) -> None:
        asyncio.create_task(self.refresh_data(force=True))

    def _switch_category(self, category: str) -> None:
        self.category = category
        self._filter_text = ""
        self.query_one("#screener-filter", Input).value = ""
        asyncio.create_task(self.refresh_data(force=False))

    def action_gainers(self) -> None:
        self._switch_category("gainers")

    def action_losers(self) -> None:
        self._switch_category("losers")

    def action_active(self) -> None:
        self._switch_category("active")

    def action_turnover(self) -> None:
        self._switch_category("turnover")

    def action_unusual(self) -> None:
        self._switch_category("unusual-volume")

    def action_toggle_live(self) -> None:
        self.live_enabled = not self.live_enabled
        self.set_payload(self.payload)

    def action_focus_filter(self) -> None:
        self.query_one("#screener-filter", Input).focus()

    def action_first_row(self) -> None:
        if self.visible_rows:
            self.query_one(DataTable).move_cursor(row=0, column=0)

    def action_last_row(self) -> None:
        if self.visible_rows:
            self.query_one(DataTable).move_cursor(row=len(self.visible_rows) - 1, column=0)

    def action_page_up(self) -> None:
        table = self.query_one(DataTable)
        table.move_cursor(row=max(0, table.cursor_coordinate.row - max(table.size.height - 3, 1)), column=0)

    def action_page_down(self) -> None:
        table = self.query_one(DataTable)
        table.move_cursor(row=min(max(len(self.visible_rows) - 1, 0), table.cursor_coordinate.row + max(table.size.height - 3, 1)), column=0)

    @on(Input.Changed, "#screener-filter")
    def filter_changed(self, event: Input.Changed) -> None:
        self._filter_text = event.value
        self._render_table()

    @on(Input.Submitted, "#screener-filter")
    def filter_submitted(self, event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

    @on(DataTable.RowSelected, "#screener-table")
    def row_selected(self, event: DataTable.RowSelected) -> None:
        item = self._table_key_to_row.get(str(event.row_key.value))
        if item:
            self.post_message(self.SymbolSelected(item["symbol"]))
            self.dismiss()


class IndiaStockDetailScreen(ModalScreen):
    """Drill-down view for quote metrics, OHLC chart and technical indicators."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
        Binding("enter", "open_chart", "Open chart"),
        Binding("w", "add_watchlist", "Add to watchlist"),
    ]

    class SymbolSelected(Message):
        def __init__(self, symbol: str):
            self.symbol = symbol
            super().__init__()

    class AddToWatchlist(Message):
        def __init__(self, symbol: str):
            self.symbol = symbol
            super().__init__()

    def __init__(self, api: ApiClient, item: dict):
        super().__init__()
        self.api = api
        self.item = item
        self.candles: list[dict] = []
        self.indicators: dict = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="stock-detail-window"):
            yield Static("STOCK DETAIL", id="stock-detail-title")
            yield Static("Loading quote history and indicators…", id="stock-detail-body")
            yield Static("Enter open chart · W add to watchlist · Esc back", id="stock-detail-help")

    async def on_mount(self) -> None:
        symbol = self.item["symbol"]
        self.query_one("#stock-detail-title", Static).update(
            Text(f"{self.item.get('nse_symbol', symbol)}  ·  {self.item.get('name', '')}", style="bold #00ff41")
        )
        try:
            self.candles = await self.api.get_candles(symbol, "1d")
            self.indicators = await self.api.get_indicators(symbol, "1d")
        except ApiError as exc:
            self.query_one("#stock-detail-body", Static).update(Text(f"History unavailable: {exc}", style="#ff4b4b"))
            return
        self.query_one("#stock-detail-body", Static).update(self._render_detail())

    def _render_detail(self):
        item = self.item
        change = float(item.get("change_pct") or 0)
        summary = Table.grid(expand=True, padding=(0, 2))
        summary.add_column(style="#00b030", ratio=1)
        summary.add_column(style="#00ff41", justify="right", ratio=1)
        metrics = [
            ("LAST TRADED PRICE", f"₹{_number(item.get('ltp'))}"),
            ("DAY CHANGE", f"{change:+.2f}%  (₹{_number(item.get('change'))})"),
            ("DAY OPEN", f"₹{_number(item.get('open'))}"),
            ("PREVIOUS CLOSE", f"₹{_number(item.get('previous_close'))}"),
            ("DAY HIGH / LOW", f"₹{_number(item.get('day_high'))} / ₹{_number(item.get('day_low'))}"),
            ("DAY RANGE POSITION", f"{_number(item.get('day_range_position_pct'), 1)}%"),
            ("52-WEEK HIGH / LOW", f"₹{_number(item.get('fifty_two_week_high'))} / ₹{_number(item.get('fifty_two_week_low'))}"),
            ("VOLUME", _compact(item.get("volume"))),
            ("AVG VOLUME", _compact(item.get("average_volume"))),
            ("RELATIVE VOLUME", f"{_number(item.get('relative_volume'))}x"),
            ("APPROX. TURNOVER", f"₹{_compact(item.get('turnover'))}"),
            ("MARKET CAP", f"₹{_compact(item.get('market_cap'))}" if item.get("market_cap") is not None else "-"),
            ("SERIES / ISIN", f"{item.get('series') or '-'} / {item.get('isin') or '-'}"),
        ]
        for label, value in metrics:
            summary.add_row(label, value)

        indicator_table = Table(title="TECHNICAL INDICATORS · DAILY", box=box.SIMPLE, expand=True)
        indicator_table.add_column("SMA 20")
        indicator_table.add_column("EMA 12")
        indicator_table.add_column("EMA 26")
        indicator_table.add_column("RSI 14")
        indicator_table.add_row(
            _number(self.indicators.get("sma20")),
            _number(self.indicators.get("ema12")),
            _number(self.indicators.get("ema26")),
            _number(self.indicators.get("rsi14")),
        )

        closes = [float(candle["close"]) for candle in self.candles if candle.get("close") is not None]
        chart_text = Text("DAILY PRICE HISTORY\n", style="bold #00ff41")
        if closes:
            chart_width = max(min(self.size.width - 12, 100), 30)
            chart = render_chart(closes[-100:], width=chart_width, height=9)
            for line in chart.lines:
                for char, is_up in zip(line, chart.column_up):
                    chart_text.append(char, style="#00ff41" if is_up else "#ff4b4b")
                chart_text.append("\n")
        else:
            chart_text.append("No daily candle history available", style="#006622")

        note = Text("Market data: Yahoo Finance snapshot · volume/turnover are indicative · not an execution feed", style="#c18b35")
        return Group(Panel(summary, title="QUOTE & MARKET STATISTICS", border_style="#006622"), indicator_table, Panel(chart_text, border_style="#006622"), note)

    def action_close(self) -> None:
        self.dismiss()

    def action_open_chart(self) -> None:
        self.post_message(self.SymbolSelected(self.item["symbol"]))
        self.dismiss()

    def action_add_watchlist(self) -> None:
        self.post_message(self.AddToWatchlist(self.item["symbol"]))
        self.query_one("#stock-detail-help", Static).update(Text(f"Watchlist request sent for {self.item['symbol']} · Esc back", style="#00ff41"))
