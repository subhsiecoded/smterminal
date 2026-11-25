from collections import deque

from rich.text import Text
from textual.widgets import Static


def build_tape_text(entries: list[tuple[str, float, bool]], offset: int, width: int) -> str:
    """Pure function: given (symbol, price, is_up) entries, a scroll
    offset, and a target width, return the plain text window to display.
    Separated from the widget so the scrolling math is testable without a
    terminal - in particular, that it wraps around cleanly and never
    returns a string shorter than `width` once there's enough content.
    """
    if not entries:
        return " " * width
    segment = "   ".join(f"{sym} {price:.2f}{'▲' if up else '▼'}" for sym, price, up in entries)
    padded = segment + "     "  # gap before it repeats
    if not padded:
        return " " * width
    doubled = padded * (width // max(len(padded), 1) + 2)
    start = offset % len(padded)
    return doubled[start : start + width]


class TickerTape(Static):
    def __init__(self, **kwargs):
        super().__init__(id="ticker-tape", **kwargs)
        self._recent: deque[tuple[str, float, bool]] = deque(maxlen=24)
        self._offset = 0

    def on_mount(self) -> None:
        self.set_interval(0.25, self._scroll)

    def push(self, symbol: str, price: float, is_up: bool) -> None:
        self._recent.append((symbol, price, is_up))

    def _scroll(self) -> None:
        self._offset += 1
        width = max(self.size.width, 1)
        plain = build_tape_text(list(self._recent), self._offset, width)
        text = Text(plain, style="#00ff80")
        self.update(text)
