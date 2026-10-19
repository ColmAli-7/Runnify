"""FIT parsing (stops and GPS glitches, laps, cadence) and run streams stored in the database."""

import json
import pathlib
import zlib
from datetime import datetime, timedelta

import pytest

from runnify.extensions import db
from runnify.models import Run, RunStream
from runnify.services.fit import Series, WatchLap, at_one_hertz, parse_fit
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


def test_parse_fit_reads_cadence_distance_and_the_watch_laps():
    samples = [(START + timedelta(seconds=i), 150, 3.0 * i, 3.0, 85) for i in range(120)]
    laps = [
        (START, 60, 2, 0, None),  # a warm-up ended with the lap button
        (START + timedelta(seconds=60), 60, 4, 7, 1),  # a recovery: newer than fitparse's names
    ]
    series = parse_fit(build_fit(samples, laps))
    assert series.cadences[0] == 170  # FIT counts one foot: 85 a minute is 170 steps
    assert series.distances[-1] == pytest.approx(357.0)
    assert series.laps == [
        WatchLap(0, 60, "warmup", "manual", None),
        WatchLap(60, 120, "recovery", "session_end", 1),
    ]


def test_a_recording_without_cadence_or_laps_has_none():
    series = parse_fit(build_fit(_samples([3.0] * 10)))
    assert series.cadences == [] and series.laps == []
    assert series.distances[:3] == [3.0, 6.0, 9.0]


def test_smart_recording_is_spread_to_one_sample_a_second():
    rows = [(START + timedelta(seconds=3 * i), 140 + i, 9.0 * i, 3.0) for i in range(11)]
    series = parse_fit(build_fit(rows))
    assert len(series) == 31  # a record every 3 seconds for 30 seconds
    assert series.timestamps[-1] - series.timestamps[0] == timedelta(seconds=30)
    assert series.heart_rates[:7] == [140, 140, 140, 141, 141, 141, 142]  # each record carries on
    assert all(pace is not None for pace in series.paces)


def test_an_auto_pause_counts_as_stopped():
    before = [(START + timedelta(seconds=i), 150, 3.0 * i, 3.0) for i in range(30)]
    after = [(START + timedelta(seconds=90 + i), 150, 90.0 + 3.0 * i, 3.0) for i in range(30)]
    series = parse_fit(build_fit(before + after))
    assert len(series) == 120
    assert series.paces[30:90] == [None] * 60 and series.heart_rates[30:90] == [None] * 60
    assert series.paces[29] is not None and series.paces[90] is not None


def test_distance_grows_evenly_across_a_gap_and_stands_still_through_a_pause():
    series = at_one_hertz(
        Series(
            timestamps=[START + timedelta(seconds=s) for s in (0, 4, 64)],
            heart_rates=[150, 150, 150],
            paces=[300.0, 300.0, 300.0],
            cadences=[170, 172, 174],
            distances=[0.0, 12.0, 20.0],
        )
    )
    assert series.distances[:5] == [0.0, 3.0, 6.0, 9.0, 12.0]
    assert series.distances[5:64] == [12.0] * 59  # paused
    assert series.cadences[3] == 170 and series.cadences[5] is None


def test_one_sample_a_second_is_left_as_it_is():
    series = Series(
        timestamps=[START + timedelta(seconds=i) for i in range(5)],
        heart_rates=[150] * 5,
        paces=[300.0] * 5,
    )
    assert at_one_hertz(series) is series


def test_streams_stored_from_smart_recording_decode_one_sample_a_second():
    sparse = Series(
        timestamps=[START + timedelta(seconds=s) for s in (0, 4, 8)],
        heart_rates=[150, 152, 154],
        paces=[300.0, 301.0, 302.0],
    )
    restored = decode(encode(sparse), START)
    assert len(restored) == 9
    assert restored.heart_rates == [150] * 4 + [152] * 4 + [154]


def test_stream_round_trip_is_compact_and_lossless_enough():
    series = parse_fit(build_fit(_samples([3.0] * 3600)))
    blob = encode(series)
    assert len(blob) < 20_000  # an hour of samples
    restored = decode(blob, series.timestamps[0])
    assert restored.timestamps == series.timestamps
    assert restored.heart_rates == series.heart_rates
    assert all(abs(a - b) <= 0.05 for a, b in zip(restored.paces, series.paces, strict=True))


def test_streams_keep_cadence_distance_and_laps():
    samples = [(START + timedelta(seconds=i), 150, 3.1 * i, 3.1, 85) for i in range(600)]
    series = parse_fit(build_fit(samples, [(START, 300, 0, 0, None), (START, 600, 1, 7, None)]))
    restored = decode(encode(series), START)
    assert restored.cadences == series.cadences
    assert restored.distances == [round(d) for d in series.distances]  # whole metres
    assert restored.laps == series.laps


def test_streams_stored_before_cadence_and_laps_still_decode():
    old = {"v": 1, "t": [0, 1, 2], "p": [300.0, 301.0, None], "h": [150, 151, 152]}
    restored = decode(zlib.compress(json.dumps(old).encode()), START)
    assert restored.paces == [300.0, 301.0, None] and restored.heart_rates == [150, 151, 152]
    assert (restored.cadences, restored.distances, restored.laps) == ([], [], [])


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
