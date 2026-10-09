"""FIT parsing (stops and GPS glitches) and run streams stored in the database."""

import pathlib
from datetime import datetime, timedelta

from runnify.extensions import db
from runnify.models import Run, RunStream
from runnify.services.fit import Series, parse_fit
from runnify.services.streams import (
    backfill_from_fit_files,
    decode,
    encode,
    load_series,
    save_stream,
)
from tests.fit_builder import build_fit

START = datetime(2026, 10, 1, 7, 0, 0)


def _samples(speeds, heart_rate=150):
    distance, rows = 0.0, []
    for i, speed in enumerate(speeds):
        distance += speed or 0.0
        rows.append((START + timedelta(seconds=i), heart_rate, distance, speed))
    return rows


def test_parse_fit_reads_pace_and_heart_rate():
    series = parse_fit(build_fit(_samples([3.333] * 20)))
    assert len(series) == 20
    assert series.timestamps[0] == START
    assert series.heart_rates[0] == 150
    assert abs(series.paces[-1] - 300.0) < 0.5  # 3.333 m/s is 5:00/km


def test_stops_and_glitches_have_no_pace():
    speeds = [3.0] * 5 + [0.5] * 3 + [12.0] + [3.0] * 5  # stopped at lights, then one GPS spike
    paces = parse_fit(build_fit(_samples(speeds))).paces
    assert paces[5:9] == [None] * 4
    assert all(p is not None for p in paces[:5] + paces[9:])


def test_stream_round_trip_is_compact_and_lossless_enough():
    series = parse_fit(build_fit(_samples([3.0] * 3600)))
    blob = encode(series)
    assert len(blob) < 20_000  # an hour of samples
    restored = decode(blob, series.timestamps[0])
    assert restored.timestamps == series.timestamps
    assert restored.heart_rates == series.heart_rates
    assert all(abs(a - b) <= 0.05 for a, b in zip(restored.paces, series.paces, strict=True))


def _run(app, user, **fields):
    with app.app_context():
        run = Run(
            user_id=user, activity_id="1", date_time=START, duration=600, distance=2000, **fields
        )
        db.session.add(run)
        db.session.commit()
        return run.id


def test_saved_streams_are_loaded_from_the_database(app, user):
    run_id = _run(app, user)
    with app.app_context():
        run = db.session.get(Run, run_id)
        save_stream(run, parse_fit(build_fit(_samples([3.0] * 30))))
        db.session.commit()
        assert len(load_series(run)) == 30


def test_runs_without_data_load_empty(app, user):
    run_id = _run(app, user)
    with app.app_context():
        assert len(load_series(db.session.get(Run, run_id))) == 0
        assert save_stream(db.session.get(Run, run_id), Series()) is None


def test_legacy_fit_files_are_read_and_backfilled(app, user, tmp_path):
    legacy = pathlib.Path(tmp_path) / "fit_files" / "1_ACTIVITY.fit"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(build_fit(_samples([3.0] * 15)))
    run_id = _run(app, user, fit_file_path=str(legacy))
    with app.app_context():
        assert len(load_series(db.session.get(Run, run_id))) == 15
        assert backfill_from_fit_files([db.session.get(Run, run_id)]) == 1
        db.session.commit()
        assert db.session.get(RunStream, run_id).sample_count == 15


def test_backfill_command(app, user, tmp_path):
    legacy = pathlib.Path(tmp_path) / "legacy.fit"
    legacy.write_bytes(build_fit(_samples([3.0] * 10)))
    _run(app, user, fit_file_path=str(legacy))
    result = app.test_cli_runner().invoke(args=["streams", "backfill"])
    assert "Stored streams for 1 run." in result.output
