"""Finding a run's laps: from the watch when its laps describe the session, else from the run."""

import math
import random
from datetime import datetime, timedelta
from itertools import pairwise

import pytest

from runnify.extensions import db
from runnify.models import Run
from runnify.services.analysis import rescore_run
from runnify.services.fit import Series, WatchLap
from runnify.services.laps import (
    Lap,
    UsualPaces,
    detect,
    find_laps,
    from_watch,
    refresh_laps,
    retype_runs,
    run_type,
    store_laps,
    usual_pace,
)
from runnify.services.streams import load_series, save_stream

START = datetime(2026, 10, 1, 7, 0)


def _session(blocks, seed=1, noise=4.0):
    """A run from ``(seconds, pace, heart rate[, cadence])`` blocks, one sample a second.

    Pace carries a little noise (``None`` is stopped); heart rate eases towards
    each block's figure with a 30-second lag, as real heart rate does.
    """
    rng = random.Random(seed)  # noqa: S311  (a repeatable simulation, not security)
    paces, heart_rates, cadences = [], [], []
    heart = blocks[0][2]
    for seconds, pace, target, *cadence in blocks:
        for _ in range(seconds):
            heart += (target - heart) / 30
            paces.append(None if pace is None else pace + rng.gauss(0, noise))
            heart_rates.append(round(heart))
            cadences.append(cadence[0] if cadence else None)
    return Series(
        timestamps=[START + timedelta(seconds=i) for i in range(len(paces))],
        heart_rates=heart_rates,
        paces=paces,
        cadences=cadences if any(c is not None for c in cadences) else [],
    )


def _kinds(laps):
    return [lap.kind for lap in laps]


def _covers(laps, length):
    """The laps run back to back from the first second to the last."""
    return (
        laps[0].start == 0
        and laps[-1].end == length
        and all(a.end == b.start for a, b in pairwise(laps))
    )


# 10 minutes easy, 6 x (3 minutes hard, 2 minutes jogging), 10 minutes easy
INTERVALS = [(600, 330, 135)] + [(180, 255, 172), (120, 360, 140)] * 6 + [(600, 345, 135)]


def test_intervals_are_found_from_pace_and_heart_rate():
    series = _session(INTERVALS)
    laps = detect(series)
    assert _kinds(laps) == ["warmup"] + ["hard", "jog"] * 5 + ["hard", "cooldown"]
    assert _covers(laps, len(series))
    reps = [lap for lap in laps if lap.kind == "hard"]
    assert all(abs(lap.seconds - 180) <= 20 for lap in reps)
    assert abs(reps[0].start - 600) <= 20


def test_a_run_walk_alternates_running_and_walking():
    laps = detect(_session([(240, 330, 140), (60, 660, 120)] * 8))
    assert _kinds(laps) == ["steady", "walk"] * 8


def test_running_between_walks_clearly_quicker_than_usual_is_hard():
    laps = detect(_session([(240, 270, 165), (60, 660, 125)] * 6), usual_pace=320)
    assert _kinds(laps) == ["hard", "walk"] * 6


def test_a_tempo_block_between_a_warm_up_and_a_cool_down():
    laps = detect(_session([(600, 340, 135), (1200, 275, 165), (600, 345, 135)]))
    assert _kinds(laps) == ["warmup", "hard", "cooldown"]
    assert abs(laps[1].start - 600) <= 20 and abs(laps[1].end - 1800) <= 20


def test_a_hilly_steady_run_stays_steady():
    # uphill is slow but hard: heart rate rises as the pace drops, which intervals never do
    length = 2400
    paces = [300 + 40 * math.sin(2 * math.pi * t / 360) for t in range(length)]
    heart = [round(150 + 8 * math.sin(2 * math.pi * (t - 20) / 360)) for t in range(length)]
    series = Series(
        timestamps=[START + timedelta(seconds=t) for t in range(length)],
        heart_rates=heart,
        paces=paces,
    )
    assert _kinds(detect(series)) == ["steady"]


def test_a_walk_break_is_its_own_lap_but_a_stop_at_the_lights_is_not():
    walked = detect(_session([(1200, 300, 150), (120, 700, 125), (1200, 300, 150)]))
    assert _kinds(walked) == ["steady", "walk", "steady"]
    stopped = detect(_session([(1200, 300, 150), (60, None, 140), (1200, 300, 150)]))
    assert _kinds(stopped) == ["steady"]


def test_cadence_tells_a_brisk_walk_from_a_slow_jog():
    # 8:30/km is quicker than walking pace, but 118 steps a minute is a walk
    laps = detect(_session([(1200, 330, 145, 168), (90, 510, 120, 118), (1200, 330, 145, 168)]))
    assert _kinds(laps) == ["steady", "walk", "steady"]


@pytest.mark.parametrize(
    "series",
    [
        Series(),
        Series(
            timestamps=[START + timedelta(seconds=i) for i in range(600)],
            heart_rates=[150] * 600,
            paces=[300.0] * 600,
        ),
    ],
    ids=["empty", "constant"],
)
def test_empty_or_constant_runs_are_one_steady_lap_or_none(series):
    laps = detect(series)
    assert _kinds(laps) == (["steady"] if len(series) else [])


def _watch(series, laps):
    """``series`` with the watch's laps: ``(seconds, intensity, trigger, step)`` in order."""
    second, watch = 0, []
    for seconds, intensity, trigger, step in laps:
        watch.append(WatchLap(second, second + seconds, intensity, trigger, step))
        second += seconds
    series.laps = watch
    return series


def test_a_structured_workout_takes_the_watch_laps():
    workout = (
        [(600, "warmup", "time", 0)]
        + [(180, "active", "time", 1), (120, "rest", "time", 2)] * 6
        + [(600, "cooldown", "session_end", 3)]
    )
    laps, source = find_laps(_watch(_session(INTERVALS), workout))
    assert source == "watch"
    assert _kinds(laps) == ["warmup"] + ["hard", "jog"] * 6 + ["cooldown"]
    assert [lap.start for lap in laps][:3] == [0, 600, 780]  # exactly the watch's laps


def test_a_suggested_easy_run_with_warm_up_and_cool_down_stays_steady():
    series = _session([(600, 340, 135), (1800, 322, 142), (300, 345, 135)])
    workout = [
        (600, "warmup", "time", 0),
        (1800, "active", "time", 1),
        (300, "cooldown", "time", 2),
    ]
    laps = from_watch(_watch(series, workout))
    assert _kinds(laps) == ["warmup", "steady", "cooldown"]


def test_laps_the_watch_ends_every_kilometre_are_ignored():
    series = _watch(_session(INTERVALS), [(300, "active", "distance", None)] * 15)
    laps, source = find_laps(series)
    assert source == "detected" and laps[1].kind == "hard"


def test_lap_button_hill_reps_are_the_hotter_laps_not_the_faster_ones():
    # uphill reps at 7:00/km, jogging back down at 5:30/km
    blocks = [(600, 340, 135)] + [(90, 420, 172), (120, 330, 140)] * 8 + [(600, 345, 135)]
    buttons = [(600, None, "manual", None)]
    buttons += [(90, None, "manual", None), (120, None, "manual", None)] * 8
    buttons += [(600, None, "session_end", None)]
    laps = from_watch(_watch(_session(blocks), buttons))
    assert _kinds(laps) == ["warmup"] + ["hard", "jog"] * 7 + ["hard", "cooldown"]
    assert all(lap.seconds == 90 for lap in laps if lap.kind == "hard")


def test_lap_button_presses_on_a_steady_run_say_nothing_about_it():
    series = _session([(2400, 300, 150)])
    buttons = [(300, None, "manual", None)] * 7 + [(300, None, "session_end", None)]
    laps, source = find_laps(_watch(series, buttons))
    assert source == "detected" and _kinds(laps) == ["steady"]


def _laps(*pairs):
    """Back-to-back laps from ``(seconds, kind)`` pairs."""
    second, laps = 0, []
    for seconds, kind in pairs:
        laps.append(Lap(second, second + seconds, kind))
        second += seconds
    return laps


@pytest.mark.parametrize(
    ("laps", "seconds", "metres", "usual", "expected"),
    [
        (
            _laps((600, "warmup"), *[(180, "hard"), (120, "jog")] * 6, (600, "cooldown")),
            3000,
            9000,
            None,
            "intervals",
        ),
        (
            _laps(
                (600, "warmup"),
                (60, "hard"),
                (240, "jog"),
                (300, "hard"),
                (180, "jog"),
                (90, "hard"),
                (600, "cooldown"),
            ),
            2070,
            6500,
            None,
            "fartlek",
        ),
        (_laps((600, "warmup"), (1200, "hard"), (600, "cooldown")), 2400, 7500, None, "tempo"),
        (
            _laps((600, "warmup"), (900, "hard"), (180, "jog"), (900, "hard"), (600, "cooldown")),
            3180,
            10000,
            None,
            "tempo",
        ),
        (_laps(*[(240, "steady"), (60, "walk")] * 8), 2400, 5500, None, "run_walk"),
        (_laps((6000, "steady")), 6000, 17000, None, "long"),
        (_laps((2400, "steady")), 2400, 9000, 320, "tempo"),  # 4:27/km against a usual 5:20/km
        (_laps((2400, "steady")), 2400, 9000, None, "easy"),  # no usual pace to judge it by yet
        (_laps((2400, "steady")), 2400, 7500, 320, "easy"),
    ],
    ids=[
        "intervals",
        "fartlek",
        "tempo",
        "two tempo blocks",
        "run-walk",
        "long",
        "quick",
        "first run",
        "easy",
    ],
)
def test_the_kind_of_run_follows_from_its_laps(laps, seconds, metres, usual, expected):
    assert run_type(laps, seconds, metres, usual) == expected


def _run(user, series, activity_id="1", **fields):
    run = Run(
        user_id=user,
        activity_id=activity_id,
        date_time=series.timestamps[0] if len(series) else START,
        duration=len(series),
        distance=fields.pop("distance", 8000),
        **fields,
    )
    db.session.add(run)
    db.session.flush()
    save_stream(run, series)
    return run


def test_laps_are_stored_with_what_each_lap_covered(app, user):
    with app.app_context():
        run = _run(user, _session(INTERVALS), distance=9000)
        refresh_laps(run, load_series(run))
        db.session.commit()
        stored = db.session.get(Run, run.id)
        assert stored.laps_source == "detected" and stored.run_type == "intervals"
        assert [lap.kind for lap in stored.laps][:3] == ["warmup", "hard", "jog"]
        rep = stored.laps[1]
        assert rep.position == 1 and rep.moving_seconds == rep.end_second - rep.start_second
        assert rep.distance == pytest.approx(180 * 1000 / 255, rel=0.05)  # 3 minutes at 4:15/km
        assert 155 <= rep.avg_hr <= 172


def test_laps_and_a_type_set_by_hand_are_kept(app, user):
    with app.app_context():
        run = _run(user, _session(INTERVALS), laps_source="manual", run_type="race")
        run.run_type_manual = True
        store_laps(run, load_series(run), [Lap(0, 3000, "steady")], "manual")
        refresh_laps(run, load_series(run))
        assert [lap.kind for lap in run.laps] == ["steady"] and run.run_type == "race"


def test_a_run_is_judged_against_the_runners_usual_pace_once_there_is_one(app, user):
    with app.app_context():
        quick = _run(user, _session([(2400, 265, 160)]), "quick", distance=9050)
        refresh_laps(quick, load_series(quick))
        assert quick.run_type == "easy"  # nothing to compare it with yet
        for n in range(3):
            _run(user, _session([(2400, 320, 145)], seed=n), f"easy{n}", distance=7500)
        retype_runs(user)
        assert quick.run_type == "tempo"
        assert usual_pace(user, exclude=quick.id) == pytest.approx(320)


@pytest.mark.parametrize("count", [0, 3, 4, 5, 8, 9])
def test_usual_paces_for_many_runs_match_one_run_at_a_time(count):
    rng = random.Random(count)  # noqa: S311  (test data)
    paces = {n: rng.choice([300.0, 312.5, rng.uniform(250, 400)]) for n in range(count)}
    usual = UsualPaces(paces)
    for left_out in [*paces, None]:
        assert usual.excluding(left_out) == usual_pace(0, exclude=left_out, paces=paces)
    if count == 4:  # the median of the three others, ties and all
        ordered = sorted(paces.values())
        assert usual.excluding(0) == sorted(p for n, p in paces.items() if n)[1]
        assert usual.excluding(None) == (ordered[1] + ordered[2]) / 2


def test_rescoring_finds_the_laps(app, user):
    with app.app_context():
        run = _run(user, _session([(600, 330, 135), (1200, 275, 165), (600, 345, 135)]))
        rescore_run(run)
        assert [lap.kind for lap in run.laps] == ["warmup", "hard", "cooldown"]
        assert run.run_type == "tempo"
