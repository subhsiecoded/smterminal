from rich.console import Group
from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

from ..ascii_chart import render_chart


class ChartHeader(Static):
    def set_info(self, symbol: str, last: float | None, lo: float, hi: float, interval: str) -> None:
        text = Text()
        text.append(f" {symbol} ", style="bold #00ff41 on #00341a")
        text.append(f"  [{interval}]  ", style="#00b030")
        if last is not None:
            text.append(f"last {last:.2f}   ", style="#00ff41")
        text.append(f"hi {hi:.2f}  lo {lo:.2f}", style="#006622")
        self.update(text)


class ChartBody(Static):
    """Renders the ASCII chart sized to however big this widget actually
    is right now - recomputed on every refresh rather than assuming a
    fixed terminal size, so it stays correct across resizes.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._closes: list[float] = []

    def set_closes(self, closes: list[float]) -> None:
        self._closes = closes
        self.refresh()

    def render(self) -> Group:
        width = max(self.size.width, 1)
        height = max(self.size.height, 1)
        if not self._closes:
            return Group(Text("Loading…", style="#006622"))

        result = render_chart(self._closes, width=width, height=height)
        lines = []
        for line in result.lines:
            text = Text()
            for ch, is_up in zip(line, result.column_up):
                text.append(ch, style="#00ff41" if is_up else "#ff3b3b")
            lines.append(text)
        return Group(*lines)


class IndicatorsRow(Static):
    def set_indicators(self, data: dict) -> None:
        def fmt(key: str, label: str) -> str:
            value = data.get(key)
            return f"{label} {value:.2f}" if value is not None else f"{label} -"

        text = Text(
            "  ".join(
                [fmt("sma20", "SMA20"), fmt("ema12", "EMA12"), fmt("ema26", "EMA26"), fmt("rsi14", "RSI14")]
            ),
            style="#00b030",
        )
        self.update(text)


class ChartPanel(Vertical):
    def __init__(self, **kwargs):
        super().__init__(id="center-panel", **kwargs)

    def compose(self):
        yield ChartHeader(id="chart-header")
        yield ChartBody(id="chart-body")
        yield IndicatorsRow(id="indicators-row")

    def set_data(self, symbol: str, candles: list[dict], interval: str) -> None:
        closes = [c["close"] for c in candles]
        last = closes[-1] if closes else None
        lo = min(closes) if closes else 0.0
        hi = max(closes) if closes else 0.0
        self.query_one(ChartHeader).set_info(symbol, last, lo, hi, interval)
        self.query_one(ChartBody).set_closes(closes)

    def set_indicators(self, data: dict) -> None:
        self.query_one(IndicatorsRow).set_indicators(data)
