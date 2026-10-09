"""Run streams: each run's pace and heart-rate samples, stored in the database.

Hosts such as Render wipe the local disk on every deploy, so FIT files kept on
disk would vanish. Instead the parsed samples are stored compactly (offsets in
seconds, pace to 0.1 s/km, whole-beat heart rate, zlib-compressed JSON; a
one-hour run is roughly 15 KB). Raw FIT files are not kept at all.
"""

import json
import logging
import zlib
from datetime import timedelta
from pathlib import Path

from runnify.extensions import db
from runnify.models import RunStream
from runnify.services.fit import Series, parse_fit

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1


def encode(series):
    """Compress a :class:`Series` into bytes (timestamps become offsets from the first sample)."""
    start = series.timestamps[0]
    payload = {
        "v": FORMAT_VERSION,
        "t": [int((t - start).total_seconds()) for t in series.timestamps],
        "p": [None if p is None else round(p, 1) for p in series.paces],
        "h": [None if h is None else int(h) for h in series.heart_rates],
    }
    return zlib.compress(json.dumps(payload, separators=(",", ":")).encode(), level=9)


def decode(blob, started_at):
    """Rebuild a :class:`Series` from :func:`encode` output and the first sample's time."""
    payload = json.loads(zlib.decompress(blob))
    return Series(
        timestamps=[started_at + timedelta(seconds=s) for s in payload["t"]],
        heart_rates=payload["h"],
        paces=payload["p"],
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
