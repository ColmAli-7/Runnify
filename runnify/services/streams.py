"""Run streams: each run's pace and heart-rate samples, stored in the database.

Hosts such as Render wipe the local disk on every deploy, so FIT files kept on
disk would vanish. Instead the parsed samples are stored compactly (offsets in
seconds, pace to 0.1 s/km, whole-beat heart rate, zlib-compressed JSON; a
one-hour run is roughly 15 KB). Raw FIT files are not kept at all.

Format 2 adds cadence (``"c"``, steps a minute), distance (``"d"``, whole
metres, each written as the step from the one before, which compresses to
almost nothing) and the watch's laps (``"l"``). Format 1 streams still read.
"""

import json
import logging
import zlib
from datetime import timedelta
from pathlib import Path

from runnify.extensions import db
from runnify.models import RunStream
from runnify.services.fit import Series, WatchLap, at_one_hertz, parse_fit

logger = logging.getLogger(__name__)

FORMAT_VERSION = 2


def _steps(values):
    """Whole numbers, each written as the step from the last known one (``None`` kept)."""
    steps, last = [], None
    for value in values:
        if value is None:
            steps.append(None)
            continue
        whole = round(value)
        steps.append(whole if last is None else whole - last)
        last = whole
    return steps


def _totals(steps):
    """Undo :func:`_steps`."""
    totals, last = [], None
    for step in steps:
        if step is None:
            totals.append(None)
            continue
        last = step if last is None else last + step
        totals.append(last)
    return totals


def encode(series):
    """Compress a :class:`Series` into bytes (timestamps become offsets from the first sample)."""
    start = series.timestamps[0]
    payload = {
        "v": FORMAT_VERSION,
        "t": [int((t - start).total_seconds()) for t in series.timestamps],
        "p": [None if p is None else round(p, 1) for p in series.paces],
        "h": [None if h is None else int(h) for h in series.heart_rates],
    }
    if series.cadences:
        payload["c"] = [None if c is None else int(c) for c in series.cadences]
    if series.distances:
        payload["d"] = _steps(series.distances)
    if series.laps:
        payload["l"] = [
            [lap.start, lap.end, lap.intensity, lap.trigger, lap.step] for lap in series.laps
        ]
    return zlib.compress(json.dumps(payload, separators=(",", ":")).encode(), level=9)


def decode(blob, started_at):
    """Rebuild a :class:`Series` from :func:`encode` output and the first sample's time.

    Streams stored from smart recording are spread to one sample a second here.
    """
    payload = json.loads(zlib.decompress(blob))
    return at_one_hertz(
        Series(
            timestamps=[started_at + timedelta(seconds=s) for s in payload["t"]],
            heart_rates=payload["h"],
            paces=payload["p"],
            cadences=payload.get("c", []),
            distances=_totals(payload.get("d", [])),
            laps=[WatchLap(*lap) for lap in payload.get("l", [])],
        )
    )


def save_stream(run, series):
    """Store ``series`` as ``run``'s stream (replacing any previous one). Empty series are ignored."""
    if not len(series):
        return None
    stream = db.session.get(RunStream, run.id) or RunStream(run_id=run.id)
    stream.started_at = series.timestamps[0]
    stream.sample_count = len(series)
    stream.samples = encode(series)
    db.session.add(stream)
    return stream


def stored_format(run):
    """The format of ``run``'s stored stream (see :data:`FORMAT_VERSION`), or 0 with none."""
    stream = db.session.get(RunStream, run.id)
    if stream is None:
        return 0
    return json.loads(zlib.decompress(stream.samples)).get("v", 1)


def load_series(run):
    """Return ``run``'s samples: from its stored stream, or a legacy FIT file, or empty."""
    stream = db.session.get(RunStream, run.id)
    if stream is not None:
        return decode(stream.samples, stream.started_at)
    if run.fit_file_path and Path(run.fit_file_path).is_file():
        try:
            return parse_fit(run.fit_file_path)
        except Exception:  # a corrupt or truncated legacy file
            logger.warning("Could not read FIT file for run %s", run.id)
    return Series()


def backfill_from_fit_files(runs):
    """Create streams for runs that only have a legacy FIT file on disk; returns how many."""
    created = 0
    for run in runs:
        if db.session.get(RunStream, run.id) is not None:
            continue
        series = load_series(run)
        if len(series) and save_stream(run, series):
            created += 1
    return created
