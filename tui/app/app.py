import asyncio

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input

from . import config, storage
from .client import ApiClient, ApiError
from .tickstream import TickStream
from .screens.india_screener import IndiaScreenerScreen, IndiaStockDetailScreen
from .widgets.banner import Banner
from .widgets.chart import ChartPanel
from .widgets.command_bar import CommandBar
from .widgets.side_panel import SidePanel
from .widgets.ticker_tape import TickerTape
from .widgets.watchlist import WatchlistPanel

CHART_REFRESH_SECONDS = 15
SAFETY_RESEED_SECONDS = 60
NARROW_WIDTH = 95       # below this, drop the side panel (movers/news/top-of-book)
VERY_NARROW_WIDTH = 60  # below this, drop the watchlist too - chart-only

HELP_TEXT = (
    "add SYM · rm SYM · select SYM · search QUERY · india [QUERY] · "
    "india-movers gainers|losers|active|turnover|unusual-volume [filters] · "
    "movers gainers|losers|active · news · "
    "interval 1m|5m|15m|1h|1d|1w · quit"
)


class MarketTerminalApp(App):
    CSS_PATH = "terminal.tcss"
    TITLE = "MARKET TERMINAL"

    BINDINGS = [
        Binding("slash", "focus_command", "Command", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, api_client: ApiClient | None = None, tick_stream: TickStream | None = None):
        super().__init__()
        self.api = api_client or ApiClient()
        self.watched: list[str] = storage.load_watchlist()
        self.selected: str = self.watched[0] if self.watched else "AAPL"
        self.interval = "1d"
        self.quotes: dict[str, dict] = {}
        self.tick_stream = tick_stream or TickStream(self._all_subscribed_symbols())
        self._ws_task: asyncio.Task | None = None

    def _all_subscribed_symbols(self) -> list[str]:
        # Defensive: never let an accidentally persisted command label enter
        # quote polling or the WebSocket subscription list.
        from .storage import _clean_symbols
        selected = _clean_symbols([self.selected])
        return list(dict.fromkeys([*_clean_symbols(self.watched), *selected]))

    def _main_widget(self, selector):
        """Query the base terminal screen even while a modal screener is on top.

        Textual screens have separate DOM trees; tick callbacks and watchlist
        events must keep updating the underlying dashboard while overlays are open.
        """
        if self.screen_stack:
            return self.screen_stack[0].query_one(selector)
        return self.query_one(selector)

    def compose(self) -> ComposeResult:
        yield Banner(id="banner")
        with Horizontal(id="body"):
            yield WatchlistPanel(self.watched)
            yield ChartPanel()
            yield SidePanel()
        yield TickerTape()
        yield CommandBar()

    async def on_mount(self) -> None:
        self._ws_task = asyncio.create_task(self.tick_stream.run(self._on_tick, self._on_ws_status))
        await self._seed_quotes()
        await self._refresh_chart()
        self.set_interval(CHART_REFRESH_SECONDS, lambda: asyncio.create_task(self._refresh_chart()))
        self.set_interval(SAFETY_RESEED_SECONDS, lambda: asyncio.create_task(self._seed_quotes()))

    def on_resize(self, event: events.Resize) -> None:
        """Side panels are fixed-width; below a certain terminal width
        there's no room left for a usable chart. Caught by actually
        resizing the app under test and asserting the chart never
        collapses to zero columns - it did, before this handler existed.
        """
        try:
            body = self._main_widget("#body")
        except Exception:
            return  # not mounted yet
        width = event.size.width
        body.set_class(width < NARROW_WIDTH, "narrow")
        body.set_class(width < VERY_NARROW_WIDTH, "very-narrow")

    async def on_unmount(self) -> None:
        self.tick_stream.stop()
        if self._ws_task:
            self._ws_task.cancel()
        await self.api.close()

    # ── Data loading ──────────────────────────────────────────────────

    async def _seed_quotes(self) -> None:
        symbols = self._all_subscribed_symbols()
        try:
            quotes = await self.api.get_quotes_batch(symbols)
        except ApiError as exc:
            self._main_widget(CommandBar).set_feedback(f"[seed] {exc}")
            return
        for quote in quotes:
            self._merge_quote(quote)

    async def _refresh_chart(self) -> bool:
        """Returns whether the refresh actually succeeded - callers that
        follow up with their own feedback message (like the `select`
        command) need this so they don't overwrite a real fetch error
        with a false "success" message.
        """
        try:
            candles = await self.api.get_candles(self.selected, self.interval)
            indicators = await self.api.get_indicators(self.selected, self.interval)
        except ApiError as exc:
            self._main_widget(CommandBar).set_feedback(f"[chart] {exc}")
            return False
        self._main_widget(ChartPanel).set_data(self.selected, candles, self.interval)
        self._main_widget(ChartPanel).set_indicators(indicators)
        self._main_widget(SidePanel).refresh_if_topbook(self.selected, self.quotes.get(self.selected))
        return True

    # ── Tick stream callbacks (called from the TickStream background task) ──

    async def _on_tick(self, tick: dict) -> None:
        self._merge_quote(tick)

    async def _on_ws_status(self, status: str) -> None:
        self._main_widget(Banner).status = status

    def _merge_quote(self, tick: dict) -> None:
        symbol = tick.get("symbol")
        if not symbol:
            return
        from .storage import _clean_symbols
        valid = _clean_symbols([symbol])
        if not valid:
            return
        symbol = valid[0]
        merged = {**self.quotes.get(symbol, {}), **{k: v for k, v in tick.items() if v is not None}}
        self.quotes[symbol] = merged

        ltp = merged.get("ltp")
        change_pct = merged.get("change_pct")
        if ltp is not None:
            if symbol in self.watched:
                last_text = f"{ltp:,.2f}"
                if change_pct is not None:
                    style = "up" if change_pct >= 0 else "down"
                    chg_text = Text(f"{change_pct:+.2f}%", style=style)
                else:
                    chg_text = Text("-", style="dim")
                self._main_widget(WatchlistPanel).update_quote(symbol, last_text, chg_text)
            self._main_widget(TickerTape).push(symbol, ltp, (change_pct or 0) >= 0)

        if symbol == self.selected:
            self._main_widget(SidePanel).refresh_if_topbook(symbol, merged)

    # ── Selection ────────────────────────────────────────────────────

    async def select_symbol(self, symbol: str) -> bool:
        from .storage import _clean_symbols
        valid = _clean_symbols([symbol])
        if not valid:
            self._main_widget(CommandBar).set_feedback(f"'{symbol}' is a command label or invalid ticker; use 'india-movers gainers' for the NSE screener")
            return False
        self.selected = valid[0]
        self.tick_stream.update_symbols(self._all_subscribed_symbols())
        if self.selected not in self.quotes:
            try:
                quote = await self.api.get_quote(self.selected)
                self._merge_quote(quote)
            except ApiError:
                pass  # chart refresh below will still surface a clear error if the symbol is bad
        return await self._refresh_chart()

    def on_watchlist_panel_symbol_selected(self, event: WatchlistPanel.SymbolSelected) -> None:
        asyncio.create_task(self.select_symbol(event.symbol))

    # ── Watchlist + screener helpers ──────────────────────────────────

    async def _add_watchlist_symbols(self, symbols: list[str]) -> None:
        from .storage import _clean_symbols
        normalized = _clean_symbols(symbols)
        rejected = [symbol for symbol in symbols if symbol and symbol.upper() not in normalized and symbol.upper() not in self.watched]
        if rejected:
            self._main_widget(CommandBar).set_feedback(f"ignored invalid/command symbols: {', '.join(rejected)}")
        added = [symbol for symbol in normalized if symbol not in self.watched]
        if not added:
            self._main_widget(CommandBar).set_feedback("all requested symbols are already in the watchlist")
            return
        self.watched.extend(added)
        storage.save_watchlist(self.watched)
        self._main_widget(WatchlistPanel).set_symbols(self.watched)
        self.tick_stream.update_symbols(self._all_subscribed_symbols())
        await self._seed_quotes()
        self._main_widget(CommandBar).set_feedback(f"watching: {', '.join(added)}")

    async def _open_india_screener(self, args: list[str], bar: CommandBar) -> None:
        category = args[0].lower() if args else "gainers"
        aliases = {
            "top-gainers": "gainers", "top-losers": "losers", "volume": "active",
            "most-active": "active", "volume-spike": "unusual-volume", "unusual": "unusual-volume",
        }
        category = aliases.get(category, category)
        valid_categories = {"gainers", "losers", "active", "turnover", "unusual-volume", "all"}
        if category not in valid_categories:
            bar.set_feedback("usage: india-movers gainers|losers|active|turnover|unusual-volume|all [key=value ...]")
            return

        aliases_for_params = {
            "min_change": "min_change_pct", "max_change": "max_change_pct",
            "min_rvol": "min_relative_volume", "min_turnover_cr": "min_turnover_cr",
            "sort": "sort_by",
        }
        numeric_int = {"limit", "offset", "min_volume"}
        numeric_float = {
            "min_price", "max_price", "min_change_pct", "max_change_pct",
            "min_turnover", "min_relative_volume", "min_turnover_cr",
        }
        params: dict = {"category": category, "series": "EQ", "limit": 50, "offset": 0}
        try:
            for token in args[1:]:
                if "=" not in token:
                    continue
                key, value = token.split("=", 1)
                key = aliases_for_params.get(key.lower(), key.lower())
                value = value.strip()
                if key in numeric_int:
                    params[key] = int(value)
                elif key == "min_turnover_cr":
                    params["min_turnover"] = float(value) * 10_000_000
                elif key in numeric_float:
                    params[key] = float(value)
                elif key in {"series", "sort_by", "order"}:
                    params[key] = value.upper() if key == "series" else value.lower()
            if category == "unusual-volume" and "min_relative_volume" not in params:
                params["min_relative_volume"] = 1.5
        except ValueError:
            bar.set_feedback("invalid filter value - use numbers, e.g. min_change=2 min_volume=100000")
            return

        bar.set_feedback("[NSE] scanning listed equities and ranking available quotes…")
        try:
            payload = await self.api.get_india_screener(**params)
        except ApiError as exc:
            bar.set_feedback(f"[NSE screener] {exc}")
            return
        self.push_screen(IndiaScreenerScreen(self.api, payload, category, params))
        meta = payload.get("meta", {})
        bar.set_feedback(
            f"NSE screener: {payload.get('total', 0)} matches · "
            f"{meta.get('coverage_pct', 0)}% quote coverage · use ↑/↓, Enter, D, W, Space"
        )

    # ── Commands ─────────────────────────────────────────────────────

    def action_focus_command(self) -> None:
        self._main_widget("#command-input", Input).focus()

    async def on_command_bar_command_submitted(self, event: CommandBar.CommandSubmitted) -> None:
        verb, args = event.verb, event.args
        bar = self._main_widget(CommandBar)

        if verb in ("add", "watch"):
            if not args:
                bar.set_feedback("usage: add SYMBOL")
                return
            await self._add_watchlist_symbols(args)

        elif verb in ("rm", "remove", "unwatch"):
            if not args:
                bar.set_feedback("usage: rm SYMBOL")
                return
            self.watched = [s for s in self.watched if s not in args]
            storage.save_watchlist(self.watched)
            self._main_widget(WatchlistPanel).set_symbols(self.watched)
            self.tick_stream.update_symbols(self._all_subscribed_symbols())
            bar.set_feedback(f"removed: {', '.join(args)}")

        elif verb in ("select", "sel"):
            if not args:
                bar.set_feedback("usage: select SYMBOL")
                return
            ok = await self.select_symbol(args[0])
            # Only report success here - on failure, _refresh_chart already
            # set a more specific "[chart] ..." error, and this must not
            # stomp over it with a false "→ SYMBOL" success message.
            if ok:
                bar.set_feedback(f"→ {args[0]}")

        elif verb in ("search", "find"):
            query = " ".join(args)
            if not query:
                bar.set_feedback("usage: search QUERY")
                return
            try:
                results = await self.api.search(query)
            except ApiError as exc:
                bar.set_feedback(f"[search] {exc}")
                return
            if not results:
                bar.set_feedback(f"no matches for '{query}'")
            else:
                preview = "  ".join(f"{r['symbol']}={r['name']}" for r in results[:6])
                bar.set_feedback(f"results: {preview}  (select SYMBOL to jump to one)")

        elif verb == "india":
            query = " ".join(args) if args else None
            try:
                payload = await self.api.search_india(query=query)
            except ApiError as exc:
                bar.set_feedback(f"[india] {exc}")
                return
            self._main_widget(SidePanel).show_india(query, payload)
            if query:
                bar.set_feedback(f"NSE results for '{query}' - select a symbol (e.g. RELIANCE.NS) to view it")
            else:
                bar.set_feedback(
                    f"browsing NSE ({payload.get('total', 0)} listed) - "
                    "try 'india QUERY' to search, or select a symbol directly"
                )

        elif verb == "movers":
            category = (args[0].lower() if args else "gainers")
            if category not in ("gainers", "losers", "active"):
                bar.set_feedback("usage: movers gainers|losers|active")
                return
            try:
                items = await self.api.get_movers(category)
            except ApiError as exc:
                bar.set_feedback(f"[movers] {exc}")
                return
            self._main_widget(SidePanel).show_movers(category, items)
            bar.set_feedback(f"showing {category} - select a symbol to switch back to top-of-book")

        elif verb in ("india-movers", "screener", "nse"):
            await self._open_india_screener(args, bar)

        elif verb == "news":
            try:
                payload = await self.api.get_news(self.selected)
            except ApiError as exc:
                bar.set_feedback(f"[news] {exc}")
                return
            self._main_widget(SidePanel).show_news(self.selected, payload)
            bar.set_feedback(f"news for {self.selected}")

        elif verb in ("interval", "int"):
            valid = {"1m", "5m", "15m", "1h", "1d", "1w"}
            if not args or args[0].lower() not in valid:
                bar.set_feedback(f"usage: interval one of {sorted(valid)}")
                return
            self.interval = args[0].lower()
            await self._refresh_chart()
            bar.set_feedback(f"interval → {self.interval}")

        elif verb in ("quit", "exit"):
            self.exit()

        elif verb in ("help", "?"):
            bar.set_feedback(HELP_TEXT)

        else:
            bar.set_feedback(f"unknown command '{verb}' - try: help")

    # Events from the full-screen India screener and its detail drill-down.
    async def on_india_screener_screen_symbol_selected(self, event: IndiaScreenerScreen.SymbolSelected) -> None:
        await self.select_symbol(event.symbol)

    async def on_india_screener_screen_add_to_watchlist(self, event: IndiaScreenerScreen.AddToWatchlist) -> None:
        await self._add_watchlist_symbols([event.symbol])

    async def on_india_stock_detail_screen_symbol_selected(self, event: IndiaStockDetailScreen.SymbolSelected) -> None:
        # The detail view is opened on top of the screener. Selecting "open chart"
        # should close both overlays so the main chart is immediately visible.
        self.pop_screen()
        await self.select_symbol(event.symbol)

    async def on_india_stock_detail_screen_add_to_watchlist(self, event: IndiaStockDetailScreen.AddToWatchlist) -> None:
        await self._add_watchlist_symbols([event.symbol])


def run() -> None:
    MarketTerminalApp().run()


if __name__ == "__main__":
    run()
