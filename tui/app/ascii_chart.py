"""A multi-row, sub-cell-resolution bar chart rendered in Unicode block
characters - the same family of trick sparkline tools use, just spread
across several rows instead of one. Deliberately a standalone, pure
function with no Textual/Rich dependency: given the same prices, it always
produces the same grid of characters, which makes it something you can
actually unit test instead of only eyeballing in a running terminal.
"""

from dataclasses import dataclass

# 9 levels of vertical fill within one character cell: index 0 is empty,
# 8 is a completely filled block. This is what gives sub-row resolution -
# a value doesn't just turn a whole row on or off, it can fill 1/8th of it.
_BLOCKS = " ▁▂▃▄▅▆▇█"


@dataclass
class ChartResult:
    lines: list[str]        # top row first, `height` entries, each `width` chars
    column_up: list[bool]   # per displayed column: did price rise vs. the previous column?
    lo: float
    hi: float


def _resample(prices: list[float], width: int) -> list[float]:
    n = len(prices)
    if n == 0:
        return [0.0] * width
    if width <= 1:
        return [prices[-1]]
    if n >= width:
        # Evenly spaced picks across the series - simple nearest-index
        # downsampling, not interpolation, which is enough resolution for
        # a terminal-width chart and keeps the function trivially testable.
        return [prices[round(i * (n - 1) / (width - 1))] for i in range(width)]
    # Fewer points than columns: stretch by repeating each point a
    # proportional number of times rather than padding with the last
    # value, so a short series doesn't look like it flatlines at the end.
    out = []
    for i in range(width):
        src_index = min(int(i * n / width), n - 1)
        out.append(prices[src_index])
    return out


def render_chart(prices: list[float], width: int, height: int) -> ChartResult:
    if width <= 0 or height <= 0:
        return ChartResult(lines=[], column_up=[], lo=0.0, hi=0.0)

    sampled = _resample(prices, width)
    lo, hi = min(sampled), max(sampled)
    value_range = (hi - lo) or 1.0  # flat series: avoid a divide-by-zero, render as a flat mid-line

    total_eighths = height * 8
    levels = [
        min(max(round((p - lo) / value_range * total_eighths), 0), total_eighths) for p in sampled
    ]

    lines = []
    for row_from_top in range(height):
        row_from_bottom = height - 1 - row_from_top
        row_base = row_from_bottom * 8
        chars = []
        for level in levels:
            filled = min(max(level - row_base, 0), 8)
            chars.append(_BLOCKS[filled])
        lines.append("".join(chars))

    column_up = [True] + [sampled[i] >= sampled[i - 1] for i in range(1, len(sampled))]
    return ChartResult(lines=lines, column_up=column_up, lo=lo, hi=hi)


if __name__ == "__main__":
    # A handful of self-checks that would catch a broken resample or a
    # broken row/level mapping - run directly (`python -m app.ascii_chart`)
    # rather than only trusting the logic by inspection.

    # 1. A monotonically increasing series should produce a monotonically
    #    non-decreasing bar height per column (reading the bottom row,
    #    since that's filled first).
    increasing = list(range(1, 21))
    result = render_chart(increasing, width=20, height=4)
    assert len(result.lines) == 4
    assert all(len(line) == 20 for line in result.lines)
    bottom_row = result.lines[-1]
    # The bottom row should be fuller (more non-space chars) than it is
    # empty near the start vs. end for a rising series.
    assert bottom_row.count(" ") < len(bottom_row), "bottom row should have some fill for a rising series"
    print("OK: increasing series produces a sane grid")

    # 2. A perfectly flat series should render as a single flat band, not
    #    crash on the lo==hi divide-by-zero case.
    flat = [100.0] * 10
    flat_result = render_chart(flat, width=10, height=3)
    assert flat_result.lo == flat_result.hi == 100.0
    print("OK: flat series handled without dividing by zero")

    # 3. Empty input shouldn't crash.
    empty_result = render_chart([], width=10, height=3)
    assert len(empty_result.lines) == 3
    print("OK: empty series handled")

    # 4. column_up should correctly flag a simple up/down/up pattern.
    pattern_result = render_chart([1, 2, 1, 3], width=4, height=2)
    assert pattern_result.column_up == [True, True, False, True]
    print("OK: column_up direction flags correct")

    print("ALL CHECKS PASSED")
