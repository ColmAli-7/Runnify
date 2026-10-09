"""SVG chart geometry, computed on the server.

Charts are inline SVG drawn from this geometry, so they appear without
JavaScript and never shift the layout. Positions are percentages of the plot,
and lines are drawn in a stretched ``BOX`` x ``BOX`` square, so a chart fills
whatever size CSS gives it while its text and strokes stay crisp. Nothing
needs an inline style, which keeps the strict Content-Security-Policy intact.
Scripts only add interactivity.
"""

from dataclasses import dataclass, field
from statistics import quantiles
from typing import ClassVar

BOX = 1000  # polyline coordinates run from 0 to BOX on both axes


def _pct(fraction):
    return round(fraction * 100, 2)


def _bucket_means(values, buckets):
    """Average ``values`` into ``buckets`` groups, keeping ``None`` where a group is empty."""
    size = len(values) / buckets
    means = []
    for b in range(buckets):
        start = int(b * size)
        chunk = [v for v in values[start : max(int((b + 1) * size), start + 1)] if v is not None]
        means.append(sum(chunk) / len(chunk) if chunk else None)
    return means


def _clock(seconds):
    """Elapsed time as on a watch: ``600`` -> ``"10:00"``, ``3600`` -> ``"1:00:00"``."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _pace_label(seconds_per_km):
    total = round(seconds_per_km)
    return f"{total // 60}:{total % 60:02d}"


@dataclass
class Band:
    """A stretch of a run chart, usually one song."""

    x: float  # percent from the left
    width: float  # percent of the plot
    label: str
    kind: str = "normal"  # "best", "worst", "context" or "normal"
    index: int = 0
    start: int = 0  # seconds into the run
    end: int = 0


@dataclass
class RunChart:
    """A value-over-time chart (pace or heart rate) with song bands."""

    box: ClassVar[int] = BOX
    seconds: int = 0  # length of the run
    top: float = 0.0  # the value at the top edge
    bottom: float = 0.0  # the value at the bottom edge
    lines: list[str] = field(default_factory=list)  # polyline points; a stop splits the line
    bands: list[Band] = field(default_factory=list)
    y_ticks: list[tuple[float, str]] = field(default_factory=list)  # (percent from top, label)
    x_ticks: list[tuple[float, str]] = field(default_factory=list)  # (percent from left, time)
    points: list[float | None] = field(default_factory=list)  # the averaged values drawn

    @property
    def empty(self):
        return not self.lines


def _time_chart(values, songs, points, max_x_ticks, *, higher_is_up, steps, label, min_margin):
    """Lay out ``values`` (one per second, ``None`` for gaps) over time; see :func:`run_chart`."""
    total = len(values)
    chart = RunChart(seconds=total)
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return chart

    if len(present) >= 20:
        cuts = quantiles(present, n=20)
        low, high = cuts[0], cuts[-1]  # ignore the most extreme 5% at each end
    else:
        low, high = min(present), max(present)
    margin = max((high - low) * 0.12, min_margin)
    low, high = low - margin, high + margin
    chart.top, chart.bottom = (
        (round(high, 1), round(low, 1)) if higher_is_up else (round(low, 1), round(high, 1))
    )

    def x_at(second):
        return second / max(total - 1, 1)

    def y_at(value):
        share = (min(max(value, low), high) - low) / (high - low)
        return 1 - share if higher_is_up else share

    buckets = min(points, total)
    chart.points = [None if v is None else round(v, 1) for v in _bucket_means(values, buckets)]
    line = []
    for i, value in enumerate(chart.points):
        if value is None:
            if len(line) > 1:
                chart.lines.append(" ".join(line))
            line = []
            continue
        second = (i + 0.5) * total / buckets
        line.append(f"{x_at(second) * BOX:.1f},{y_at(value) * BOX:.1f}")
    if len(line) > 1:
        chart.lines.append(" ".join(line))

    for index, (start, end, band_label, kind) in enumerate(songs):
        x0, x1 = x_at(max(start, 0)), x_at(min(end, total - 1))
        if x1 > x0:
            chart.bands.append(
                Band(_pct(x0), _pct(x1 - x0), band_label, kind, index, int(start), int(end))
            )

    spread = high - low
    step = next((size for limit, size in steps if spread <= limit), steps[-1][1])
    first = int(low // step + 1) * step
    ticks = [(_pct(y_at(v)), label(v)) for v in range(first, int(high) + 1, step) if v < high]
    chart.y_ticks = sorted(ticks)

    minutes = total / 60
    every = next((m for m in (1, 2, 5, 10, 15, 20, 30, 60) if minutes / m <= max_x_ticks), 120)
    chart.x_ticks = [
        (_pct(x_at(m * 60)), _clock(m * 60))
        for m in range(every, int(minutes) + 1, every)
        if m * 60 < total
    ]
    return chart


def run_chart(paces, songs=(), points=240, max_x_ticks=6):
    """Lay out a pace chart, faster pace drawn higher.

    Args:
        paces: Pace samples in seconds per km, one per second (``None`` = stopped).
        songs: ``(start_second, end_second, label, kind)`` for each band.
        points: How many points to draw (samples are averaged into this many).
        max_x_ticks: The most time labels along the bottom.

    Returns:
        A :class:`RunChart`; ``chart.empty`` when there is too little movement to draw.
    """
    return _time_chart(
        paces,
        songs,
        points,
        max_x_ticks,
        higher_is_up=False,
        steps=((25, 5), (50, 10), (120, 15), (float("inf"), 30)),
        label=_pace_label,
        min_margin=4.0,
    )


def heart_chart(heart_rates, songs=(), points=240, max_x_ticks=6):
    """Lay out a heart-rate chart (beats per minute, higher drawn higher); see :func:`run_chart`."""
    return _time_chart(
        heart_rates,
        songs,
        points,
        max_x_ticks,
        higher_is_up=True,
        steps=((25, 5), (60, 10), (float("inf"), 20)),
        label=str,
        min_margin=3.0,
    )


@dataclass
class Bar:
    """One bar, in percentages of the plot."""

    x: float
    width: float
    y: float  # top edge, percent from the top
    height: float
    label: str
    value_label: str
    kind: str = "up"  # "up", "down" or "muted" (no value)

    @property
    def center(self):
        return round(self.x + self.width / 2, 2)

    @property
    def bottom(self):
        return round(self.y + self.height, 2)


@dataclass
class BarChart:
    bars: list[Bar] = field(default_factory=list)
    baseline: float = 100.0  # the zero line, percent from the top

    @property
    def empty(self):
        return all(bar.kind == "muted" for bar in self.bars)


def bar_chart(values, value_format=str, diverging=False, headroom=14.0):
    """Lay out vertical bars.

    Args:
        values: ``(label, value)`` pairs (``None`` values are drawn as empty slots).
        value_format: Formats a value for the label above (or below) its bar.
        diverging: Bars grow up from a middle zero line for positive values and
            down for negative ones (used for effects in s/km).
        headroom: Percent of the height kept clear for value labels.

    Returns:
        A :class:`BarChart`.
    """
    chart = BarChart()
    if not values:
        return chart
    present = [v for _, v in values if v is not None]
    zero = 50.0 if diverging else 100.0
    extent = max((abs(v) for v in present), default=0.0) or 1.0
    scale = (zero - headroom) / extent
    chart.baseline = zero

    slot = 100 / len(values)
    width = slot * (0.62 if len(values) > 6 else 0.44)
    for i, (label, value) in enumerate(values):
        v = value or 0.0
        h = abs(v) * scale
        chart.bars.append(
            Bar(
                x=round(i * slot + (slot - width) / 2, 2),
                width=round(width, 2),
                y=round(zero - h if v >= 0 else zero, 2),
                height=round(h, 2),
                label=label,
                value_label="" if value is None else value_format(value),
                kind="muted" if value is None else ("up" if v >= 0 else "down"),
            )
        )
    return chart
