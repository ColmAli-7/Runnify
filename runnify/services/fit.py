"""Reading Garmin ``.fit`` activity files into time series.

Pace comes from the recorded (enhanced) speed, or from the change in distance
between records when speed is missing. Samples where the runner is stopped
(slower than 15:00/km) or the GPS glitches (faster than 2:00/km) carry no
pace, so a traffic-light stop is never mistaken for slow running. The
remaining pace is lightly smoothed with an exponential moving average, and
the series is spread to one sample a second (see :func:`at_one_hertz`).
Cadence, distance and the watch's own laps are kept when the file has them.

Runnify reads the ``record`` and ``lap`` messages itself (:func:`_read_messages`),
decoding each message with one precompiled ``struct`` and skipping every field
and message it doesn't use, which is fifty times quicker than fitparse on a
watch's file. The values are exactly fitparse's. Anything the reader doesn't
expect (old devices' compressed speed and distance, arrays, relative times, a
broken file) goes to fitparse, which reads every corner of the format. The
file's own CRC isn't checked: Garmin's download is a zip, whose CRC-32 is.

Two things differ from fitparse on purpose. Developer (Connect IQ) fields are
never read, so one named like the watch's own (``heart_rate``, say) can't
replace the watch's value, as it could with fitparse. And fields Runnify
doesn't use are stepped over whatever their size, so a file fitparse refused
for an oddly sized one of those still gives its samples.
"""

import io
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from fitparse import FitFile

STOPPED_PACE = 900.0  # s/km; slower than 15:00/km counts as stopped
GLITCH_PACE = 120.0  # s/km; faster than 2:00/km is a GPS spike
SMOOTHING = 0.2  # EMA alpha: higher reacts faster
GAP_FILL = 10  # seconds; a longer gap between records (auto-pause) counts as stopped
# FIT's lap intensities; fitparse 1.2 names only the first four
INTENSITIES = {
    0: "active",
    1: "rest",
    2: "warmup",
    3: "cooldown",
    4: "recovery",
    5: "interval",
    6: "other",
}

# ---- reading FIT messages ----------------------------------------------------

FIT_EPOCH = datetime(1989, 12, 31)  # FIT times are seconds since this moment, UTC
RELATIVE_TIME = 0x10000000  # FIT times below this count from power-on, not the epoch
# the integer base types read here: identifier -> (struct code, the "invalid" value)
_INTEGERS = {
    0x00: ("B", 0xFF),  # enum
    0x01: ("b", 0x7F),
    0x02: ("B", 0xFF),
    0x83: ("h", 0x7FFF),
    0x84: ("H", 0xFFFF),
    0x85: ("i", 0x7FFFFFFF),
    0x86: ("I", 0xFFFFFFFF),
    0x0A: ("B", 0),  # the "z" types count 0 as invalid
    0x8B: ("H", 0),
    0x8C: ("I", 0),
    0x8E: ("q", 0x7FFFFFFFFFFFFFFF),
    0x8F: ("Q", 0xFFFFFFFFFFFFFFFF),
    0x90: ("Q", 0),
}
TIMESTAMP = 253  # the field number every message type uses for its time
# fitparse's names for the enums Runnify reads (numbers it doesn't name stay numbers)
_ENUMS = {
    "intensity": {0: "active", 1: "rest", 2: "warmup", 3: "cooldown"},
    "lap_trigger": {
        0: "manual",
        1: "time",
        2: "distance",
        3: "position_start",
        4: "position_lap",
        5: "position_waypoint",
        6: "position_marked",
        7: "session_end",
        8: "fitness_equipment",
    },
    "wkt_step_index": {4095: "mask", 28672: "reserved", 32768: "selected"},
}
_SCALES = {
    "distance": 100,
    "speed": 1000,
    "enhanced_speed": 1000,
    "fractional_cadence": 128,
    "total_elapsed_time": 1000,
}
_TIMES = {"timestamp", "start_time"}
# global message number -> {field number: name}, for the fields Runnify uses
_FIELDS = {
    20: {  # record
        TIMESTAMP: "timestamp",
        3: "heart_rate",
        4: "cadence",
        5: "distance",
        6: "speed",
        53: "fractional_cadence",
        73: "enhanced_speed",
    },
    19: {  # lap
        TIMESTAMP: "timestamp",
        2: "start_time",
        7: "total_elapsed_time",
        23: "intensity",
        24: "lap_trigger",
        71: "wkt_step_index",
    },
}
_EXPANDED = {(20, 8)}  # record.compressed_speed_distance (old devices): fitparse expands it


class _Unusual(Exception):
    """Something the quick reader leaves to fitparse."""


def _definition(endian, number, fields, extra):
    """How to read a data message: ``(size, message number, unpack, names, invalid values)``.

    ``fields`` are ``(number, size, base type)``; ``extra`` is the bytes of
    developer fields after them. One ``struct`` reads every field Runnify uses
    and steps over the rest.
    """
    wanted = _FIELDS.get(number, {TIMESTAMP: "timestamp"})
    layout, names, invalids, size = [endian], [], [], extra
    for field_number, field_size, base in fields:
        size += field_size
        if (number, field_number) in _EXPANDED:
            raise _Unusual("compressed speed and distance")
        name = wanted.get(field_number)
        code, invalid = _INTEGERS.get(base, (None, None))
        if name is None:
            layout.append(f"{field_size}x")
        elif code is None or struct.calcsize("<" + code) != field_size:
            raise _Unusual(f"{name} isn't a single integer")
        else:
            layout.append(code)
            names.append(name)
            invalids.append(invalid)
    layout.append(f"{extra}x")
    unpack = struct.Struct("".join(layout)).unpack_from if names else None
    return size, number, unpack, tuple(names), tuple(invalids)


def _value(name, raw):
    """A raw field value as fitparse gives it: scaled, named or as a datetime."""
    if raw is None:
        return None
    if name in _TIMES:
        if raw < RELATIVE_TIME:
            raise _Unusual("a time relative to power-on")
        return FIT_EPOCH + timedelta(seconds=raw)
    if name in _SCALES:
        return raw / _SCALES[name]
    if name in _ENUMS:
        return _ENUMS[name].get(raw, raw)
    return raw


def _read_messages(data):
    """The ``record`` and ``lap`` messages of FIT ``data``, as fitparse would give them.

    Returns:
        ``(records, laps)``: lists of ``{field name: value}`` holding the fields
        Runnify uses, leaving out invalid ones.

    Raises:
        _Unusual: The data needs fitparse (or is broken, which fitparse reports).
    """
    records, laps = [], []
    unpack_size = struct.Struct("<I").unpack_from
    pos, length = 0, len(data)
    while pos < length:  # a file can hold several FIT files in a row
        header_size = data[pos]
        if header_size < 12 or data[pos + 8 : pos + 12] != b".FIT":
            raise _Unusual("not a FIT header")
        end = pos + header_size + unpack_size(data, pos + 4)[0]
        if end + 2 > length:
            raise _Unusual("cut short")
        pos += header_size
        definitions, last_time = {}, 0
        while pos < end:
            head = data[pos]
            pos += 1
            if head & 0x80 == 0 and head & 0x40:  # a definition message
                endian = ">" if data[pos + 1] else "<"
                (number,) = struct.unpack_from(endian + "H", data, pos + 2)
                count = data[pos + 4]
                pos += 5
                fields = [tuple(data[at : at + 3]) for at in range(pos, pos + 3 * count, 3)]
                pos += 3 * count
                extra = 0
                if head & 0x20:  # developer fields follow
                    developer = data[pos]
                    extra = sum(data[pos + 2 + 3 * i] for i in range(developer))
                    pos += 1 + 3 * developer
                definitions[head & 0x0F] = _definition(endian, number, fields, extra)
                continue
            compressed = head & 0x80
            local = (head >> 5) & 0x03 if compressed else head & 0x0F
            if local not in definitions:
                raise _Unusual("data before its definition")
            size, number, unpack, names, invalids = definitions[local]
            raw = {}  # invalid values are None, as fitparse has them
            if unpack:
                for name, value, invalid in zip(names, unpack(data, pos), invalids, strict=True):
                    if name == "speed":  # fitparse first expands speed into enhanced speed
                        raw["enhanced_speed"] = None if value == invalid else value
                    raw[name] = None if value == invalid else value
            pos += size
            if raw.get("timestamp") is not None:
                last_time = raw["timestamp"]
            if compressed:  # five bits of seconds since the last full time, rolling over
                offset = head & 0x1F
                last_time = (
                    (last_time & ~0x1F) + offset + (0x20 if offset < (last_time & 0x1F) else 0)
                )
                raw["timestamp"] = last_time
            if number in _FIELDS:
                fields = {name: _value(name, value) for name, value in raw.items()}
                (records if number == 20 else laps).append(fields)
        if pos != end:
            raise _Unusual("a message runs past the end")
        pos = end + 2  # the file's CRC
    return records, laps


def _fitparse_messages(data):
    """The same as :func:`_read_messages`, read by fitparse (every field it finds)."""
    records, laps = [], []
    for message in FitFile(io.BytesIO(data)).get_messages(("record", "lap")):
        fields = {f.name: f.value for f in message}
        (laps if message.name == "lap" else records).append(fields)
    return records, laps


@dataclass
class WatchLap:
    """A lap as the watch recorded it, in seconds from the run's first sample."""

    start: int
    end: int
    intensity: str | None = None  # "active", "rest", "warmup", "cooldown", "recovery", ...
    trigger: str | None = None  # "manual" (the lap button), "distance", "time", "session_end", ...
    step: int | None = None  # the workout step it belonged to, when the run followed a workout


@dataclass
class Series:
    """Time-ordered samples from one run, one a second (see :func:`at_one_hertz`).

    ``cadences`` and ``distances`` are the same length as ``timestamps``, or
    empty when the recording had none. ``laps`` holds the watch's own laps.
    """

    timestamps: list[datetime] = field(default_factory=list)
    heart_rates: list[int | None] = field(default_factory=list)
    # seconds per km; None while stopped or unknown
    paces: list[float | None] = field(default_factory=list)
    cadences: list[int | None] = field(default_factory=list)  # steps a minute
    distances: list[float | None] = field(default_factory=list)  # metres from the start
    laps: list[WatchLap] = field(default_factory=list)

    def __len__(self):
        return len(self.timestamps)

    def as_tuple(self):
        """``(timestamps, heart_rates, paces)``, the shape older callers expect."""
        return self.timestamps, self.heart_rates, self.paces


def at_one_hertz(series):
    """Return ``series`` with one sample a second, from its first sample to its last.

    Watches on "smart" recording write a record every few seconds and auto-pause
    leaves longer gaps, but charts and scoring read one sample as one second.
    A gap up to ``GAP_FILL`` seconds carries the last record's values (distance
    grows evenly across it); a longer one counts as stopped, with no pace,
    heart rate or cadence, and the distance standing still. A series that
    already has one sample a second comes back as it is.
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
    cadences = [None] * length if series.cadences else []
    distances = [None] * length if series.distances else []
    for i, offset in enumerate(offsets):
        following = offsets[i + 1] if i + 1 < len(offsets) else offset + 1
        bridged = following - offset <= GAP_FILL
        for second in range(offset, following if bridged else offset + 1):
            heart_rates[second] = series.heart_rates[i]
            paces[second] = series.paces[i]
            if cadences:
                cadences[second] = series.cadences[i]
        if distances:
            here = series.distances[i]
            there = series.distances[i + 1] if i + 1 < len(offsets) else None
            for second in range(offset, following):
                if bridged and here is not None and there is not None:
                    share = (second - offset) / (following - offset)
                    distances[second] = here + (there - here) * share
                else:
                    distances[second] = here
    return Series(
        timestamps=[start + timedelta(seconds=s) for s in range(length)],
        heart_rates=heart_rates,
        paces=paces,
        cadences=cadences,
        distances=distances,
        laps=series.laps,
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
    timestamp, _, speed, distance, _ = rows[index]
    if speed is None and index > 0 and distance is not None:
        previous_time, _, _, previous_distance, _ = rows[index - 1]
        seconds = (timestamp - previous_time).total_seconds()
        if previous_distance is not None and seconds > 0:
            speed = (distance - previous_distance) / seconds
    if not speed or speed <= 0:
        return None
    pace = 1000.0 / speed
    return pace if GLITCH_PACE <= pace <= STOPPED_PACE else None


def _cadence(fields):
    """Steps a minute, or ``None``: FIT counts one foot (``cadence`` plus its fraction)."""
    cadence = fields.get("cadence")
    if cadence is None:
        return None
    return round(2 * (cadence + (fields.get("fractional_cadence") or 0)))


def _named(value, names):
    """A FIT enum value by name; numbers fitparse doesn't name are looked up in ``names``."""
    if isinstance(value, int):
        return names.get(value, str(value))
    return value


def _watch_laps(laps, first):
    """The watch's ``lap`` messages as :class:`WatchLap`, in seconds from ``first``."""
    found = []
    for fields in laps:
        start_time, elapsed = fields.get("start_time"), fields.get("total_elapsed_time")
        if start_time is None or elapsed is None:
            continue
        start = max(round((start_time - first).total_seconds()), 0)
        step = fields.get("wkt_step_index")
        found.append(
            WatchLap(
                start=start,
                end=start + round(elapsed),
                intensity=_named(fields.get("intensity"), INTENSITIES),
                trigger=_named(fields.get("lap_trigger"), {}),
                step=step if isinstance(step, int) else None,
            )
        )
    return sorted(found, key=lambda lap: lap.start)


def _fit_bytes(fileish):
    """The bytes of FIT data given as a path, bytes or a binary file."""
    if isinstance(fileish, bytes | bytearray):
        return bytes(fileish)
    if isinstance(fileish, str | Path):
        return Path(fileish).read_bytes()
    return fileish.read()


def parse_fit(fileish):
    """Parse FIT data (a path, bytes or a binary file) into a :class:`Series`, laps included."""
    data = _fit_bytes(fileish)
    try:
        records, laps = _read_messages(data)
    except (_Unusual, struct.error, IndexError):
        records, laps = _fitparse_messages(data)
    rows = []
    for fields in records:
        if fields.get("timestamp") is not None:
            speed = fields.get("enhanced_speed")
            if speed is None:
                speed = fields.get("speed")
            rows.append(
                (
                    fields["timestamp"],
                    fields.get("heart_rate"),
                    speed,
                    fields.get("distance"),
                    _cadence(fields),
                )
            )
    rows.sort(key=lambda row: row[0])
    has_distance = any(row[3] is not None for row in rows)
    has_cadence = any(row[4] is not None for row in rows)
    return at_one_hertz(
        Series(
            timestamps=[row[0] for row in rows],
            heart_rates=[row[1] for row in rows],
            paces=_ema([_raw_pace(rows, i) for i in range(len(rows))]),
            cadences=[row[4] for row in rows] if has_cadence else [],
            distances=[row[3] for row in rows] if has_distance else [],
            laps=_watch_laps(laps, rows[0][0]) if rows else [],
        )
    )


def read_fit_to_series(fit_file_path):
    """Extract ``(timestamps, heart_rates, paces_seconds_per_km)`` from a FIT file.

    Kept for callers that work with plain lists; see :func:`parse_fit`.
    """
    return parse_fit(fit_file_path).as_tuple()
