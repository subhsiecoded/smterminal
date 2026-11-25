from rich.text import Text
from textual.widgets import Static

# Pure render functions first - each takes plain data and returns a Rich
# Text, with no widget/mounting involved, so they're testable on their own
# without a running Textual app.


def render_topbook(symbol: str, quote: dict | None) -> Text:
    text = Text(f"TOP OF BOOK · {symbol}\n", style="bold #00ff41")
    if not quote:
        text.append("Waiting for a quote…", style="#006622")
        return text
    bid, ask = quote.get("bid"), quote.get("ask")
    if bid is None or ask is None:
        text.append("Not available for this symbol via the current feed.", style="#006622")
        return text
    bid_size, ask_size = quote.get("bid_size"), quote.get("ask_size")
    text.append(f"BID {bid:.2f}", style="#00ff41")
    if bid_size is not None:
        text.append(f" x{bid_size}", style="#006622")
    text.append("    ")
    text.append(f"ASK {ask:.2f}", style="#ff3b3b")
    if ask_size is not None:
        text.append(f" x{ask_size}", style="#006622")
    return text


def render_movers(category: str, items: list[dict]) -> Text:
    text = Text(f"MOVERS · {category.upper()}\n", style="bold #00ff41")
    if not items:
        text.append("No data - provider unreachable or empty.", style="#006622")
        return text
    for item in items[:12]:
        up = item.get("change_pct", 0) >= 0
        text.append(f"{item['symbol']:<8}", style="#00ff41")
        text.append(f"{item.get('price', 0):>10.2f}  ", style="#00b030")
        text.append(f"{item.get('change_pct', 0):+.2f}%\n", style="#00ff41" if up else "#ff3b3b")
    return text


def render_india(query: str | None, payload: dict) -> Text:
    """NSE's own published equity list (see backend/app/services/
    nse_universe.py), not a fuzzy third-party search - `total` here is
    the real count of matches (or of the whole exchange, with no query),
    not just how many are shown on this page.
    """
    heading = f"NSE INDIA · '{query}'" if query else "NSE INDIA · browse"
    text = Text(f"{heading}\n", style="bold #00ff41")
    results = payload.get("results", [])
    total = payload.get("total", 0)
    if not results:
        text.append("No matches." if query else "No data - NSE unreachable.", style="#006622")
        return text
    for item in results[:15]:
        text.append(f"{item['symbol']:<12}", style="#00ff41")
        text.append(f"{item.get('yahoo_symbol', ''):<14}", style="#006622")
        text.append(f"{item.get('name', '')}\n", style="#00b030")
    if total > len(results):
        text.append(f"\n({total} total - select a symbol or refine the search to narrow it down)", style="#006622")
    return text


def render_news(symbol: str, payload: dict) -> Text:
    text = Text(f"NEWS · {symbol}\n", style="bold #00ff41")
    if not payload.get("configured", True):
        text.append("Set FINNHUB_API_KEY to enable news.", style="#006622")
        return text
    items = payload.get("items", [])
    if not items:
        text.append("No recent news found.", style="#006622")
        return text
    for item in items[:10]:
        text.append(f"• {item['headline']}\n", style="#00ff41")
        if item.get("source"):
            text.append(f"  {item['source']}\n", style="#006622")
    return text


class SidePanel(Static):
    """One panel, several modes (topbook / movers / news), switched by
    command - keeps the layout simple instead of mounting/unmounting
    different widgets for each mode.
    """

    def __init__(self, **kwargs):
        super().__init__(id="side-panel", **kwargs)
        self.mode = "topbook"
        self._last_symbol = ""
        self._last_quote: dict | None = None

    def show_topbook(self, symbol: str, quote: dict | None) -> None:
        self.mode = "topbook"
        self._last_symbol = symbol
        self._last_quote = quote
        self.update(render_topbook(symbol, quote))

    def show_movers(self, category: str, items: list[dict]) -> None:
        self.mode = "movers"
        self.update(render_movers(category, items))

    def show_news(self, symbol: str, payload: dict) -> None:
        self.mode = "news"
        self.update(render_news(symbol, payload))

    def show_india(self, query: str | None, payload: dict) -> None:
        self.mode = "india"
        self.update(render_india(query, payload))

    def refresh_if_topbook(self, symbol: str, quote: dict) -> None:
        """Called on every tick for the selected symbol - only actually
        re-renders if the side panel is currently showing top-of-book for
        THIS symbol, so a tick doesn't yank the user out of a movers/news
        view they asked to see.
        """
        if self.mode == "topbook" and symbol.upper() == self._last_symbol.upper():
            self.show_topbook(symbol, quote)
