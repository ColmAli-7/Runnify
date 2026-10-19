"""Reading Garmin ``.fit`` activity files into time series.

Pace comes from the recorded (enhanced) speed, or from the change in distance
between records when speed is missing. Samples where the runner is stopped
(slower than 15:00/km) or the GPS glitches (faster than 2:00/km) carry no
pace, so a traffic-light stop is never mistaken for slow running. The
remaining pace is lightly smoothed with an exponential moving average, and
the series is spread to one sample a second (see :func:`at_one_hertz`).
"""

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fitparse import FitFile

STOPPED_PACE = 900.0  # s/km; slower than 15:00/km counts as stopped
GLITCH_PACE = 120.0  # s/km; faster than 2:00/km is a GPS spike
SMOOTHING = 0.2  # EMA alpha: higher reacts faster
GAP_FILL = 10  # seconds; a longer gap between records (auto-pause) counts as stopped


@dataclass
class Series:
    """Equal-length, time-ordered samples from one run."""

    timestamps: list[datetime] = field(default_factory=list)
    heart_rates: list[int | None] = field(default_factory=list)
    # seconds per km; None while stopped or unknown
    paces: list[float | None] = field(default_factory=list)

    def __len__(self):
        return len(self.timestamps)

    def as_tuple(self):
        """``(timestamps, heart_rates, paces)``, the shape older callers expect."""
        return self.timestamps, self.heart_rates, self.paces


def at_one_hertz(series):
    """Return ``series`` with one sample a second, from its first sample to its last.

    Watches on "smart" recording write a record every few seconds and auto-pause
    leaves longer gaps, but charts and scoring read one sample as one second.
    A gap up to ``GAP_FILL`` seconds carries the last record's values; a longer
    one counts as stopped (no pace, no heart rate). A series that already has
    one sample a second comes back as it is.
    """
    timestamps = series.timestamps
    if not timestamps:
        return series
    start = timestamps[0]
    offsets = [round((t - start).total_seconds()) for t in timestamps]
    if offsets == list(range(len(offsets))):
        return series
    length = offsets[-1] + 1
    heart_rates, paces = [None] * length, [None] * length
    for i, offset in enumerate(offsets):
        until = offsets[i + 1] if i + 1 < len(offsets) else offset + 1
        if until - offset > GAP_FILL:  # a pause: only this second has values
            until = offset + 1
        for second in range(offset, until):
            heart_rates[second] = series.heart_rates[i]
            paces[second] = series.paces[i]
    return Series(
        timestamps=[start + timedelta(seconds=s) for s in range(length)],
        heart_rates=heart_rates,
        paces=paces,
    )


def _ema(values, alpha=SMOOTHING):
    """Smooth a series with an exponential moving average, leaving ``None`` gaps as gaps.

    Args:
        values: Numeric values (may contain ``None``).
        alpha: Smoothing factor; higher reacts faster to changes.

    Returns:
        A list the same length as ``values``.
    """
    smoothed, previous = [], None
    for value in values:
        if value is None:
            smoothed.append(None)
            continue
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        smoothed.append(previous)
    return smoothed


def _raw_pace(rows, index):
    """Unsmoothed pace (s/km) for record ``index``, or ``None`` when stopped or unknown."""
    timestamp, _, speed, distance = rows[index]
    if speed is None and index > 0 and distance is not None:
        previous_time, _, _, previous_distance = rows[index - 1]
        seconds = (timestamp - previous_time).total_seconds()
        if previous_distance is not None and seconds > 0:
            speed = (distance - previous_distance) / seconds
    if not speed or speed <= 0:
        return None
    pace = 1000.0 / speed
    return pace if GLITCH_PACE <= pace <= STOPPED_PACE else None


def parse_fit(fileish):
    """Parse FIT data (a path, bytes or a binary file) into a :class:`Series`."""
    if isinstance(fileish, bytes | bytearray):
        fileish = io.BytesIO(fileish)
    rows = []
    for record in FitFile(fileish).get_messages("record"):
        fields = {f.name: f.value for f in record}
        if fields.get("timestamp") is not None:
            speed = fields.get("enhanced_speed", fields.get("speed"))
            rows.append(
                (fields["timestamp"], fields.get("heart_rate"), speed, fields.get("distance"))
            )
    rows.sort(key=lambda row: row[0])
    return at_one_hertz(
        Series(
            timestamps=[row[0] for row in rows],
            heart_rates=[row[1] for row in rows],
            paces=_ema([_raw_pace(rows, i) for i in range(len(rows))]),
        )
    )


def read_fit_to_series(fit_file_path):
    """Extract ``(timestamps, heart_rates, paces_seconds_per_km)`` from a FIT file.

    Kept for callers that work with plain lists; see :func:`parse_fit`.
    """
    return parse_fit(fit_file_path).as_tuple()
