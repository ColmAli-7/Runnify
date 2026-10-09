"""Reading Garmin ``.fit`` activity files into time series.

Pace comes from the recorded (enhanced) speed, or from the change in distance
between records when speed is missing. Samples where the runner is stopped
(slower than 15:00/km) or the GPS glitches (faster than 2:00/km) carry no
pace, so a traffic-light stop is never mistaken for slow running. The
remaining pace is lightly smoothed with an exponential moving average.
"""

import io
from dataclasses import dataclass, field
from datetime import datetime

from fitparse import FitFile

STOPPED_PACE = 900.0  # s/km; slower than 15:00/km counts as stopped
GLITCH_PACE = 120.0  # s/km; faster than 2:00/km is a GPS spike
SMOOTHING = 0.2  # EMA alpha: higher reacts faster


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
    return Series(
        timestamps=[row[0] for row in rows],
        heart_rates=[row[1] for row in rows],
        paces=_ema([_raw_pace(rows, i) for i in range(len(rows))]),
    )


def read_fit_to_series(fit_file_path):
    """Extract ``(timestamps, heart_rates, paces_seconds_per_km)`` from a FIT file.

    Kept for callers that work with plain lists; see :func:`parse_fit`.
    """
    return parse_fit(fit_file_path).as_tuple()
