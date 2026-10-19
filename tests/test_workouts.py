"""Typed workouts: read into steps, written back plainly, and lined up with the run."""

import pytest

from runnify.extensions import db
from runnify.models import Run
from runnify.services.laps import KINDS
from runnify.services.workouts import (
    NAMES,
    WorkoutError,
    describe,
    line_up,
    parse,
    steps_of,
)
from tests.test_laps import INTERVALS, _session
from tests.test_run_laps import _interval_run, _laps


@pytest.mark.parametrize(
    ("typed", "read"),
    [
        (
            "15 min warm-up, 6 x 3 min hard with 2 min jog, 10 min cool-down",
            "15 min warm-up, 6 x (3 min hard, 2 min jog), 10 min cool-down",
        ),
        (
            "10' wu, 8x400m @ 5k pace / 200m jog, 10' cd",
            "10 min warm-up, 8 x (400 m hard, 200 m jog), 10 min cool-down",
        ),
        (
            "2 km easy, 4 x 1 km hard with 90 s walk, 2 km easy",
            "2 km steady, 4 x (1 km hard, 90 s walk), 2 km steady",
        ),
        ("run 4 min walk 1 min x 8", "8 x (4 min steady, 1 min walk)"),
        (
            "Warm up 10 min then 5 x (3 min hard, 2 min easy) then cool down 10 min",
            "10 min warm-up, 5 x (3 min hard, 2 min jog), 10 min cool-down",
        ),
        ("400m x 6", "6 x 400 m hard"),
        ("3 × 1:30 hard / 1:30 jog", "3 x (90 s hard, 90 s jog)"),  # noqa: RUF001  (as phones type)
    ],
)
def test_workouts_are_read_and_written_back_plainly(typed, read):
    assert describe(parse(typed)) == read


@pytest.mark.parametrize(
    ("typed", "says"),
    [
        ("", "Write the workout out"),
        ("20 min", "Say what kind of running"),
        ("10 min easy, knee sore", "couldn't find a time or a distance in “knee sore”"),
        ("60 x 1 min hard / 1 min jog", "between 1 and 50 times"),
    ],
)
def test_what_cant_be_read_is_refused_plainly(typed, says):
    with pytest.raises(WorkoutError, match=says):
        parse(typed)


def test_every_kind_of_lap_can_be_written_back():
    assert set(NAMES) == set(KINDS)


def _ends(laps):
    return [lap.end for lap in laps]


def test_a_workout_lines_up_with_the_run():
    laps = line_up(
        parse("10 min warm-up, 6 x 3 min hard with 2 min jog, 10 min cool-down"),
        _session(INTERVALS),
    )
    assert [lap.kind for lap in laps] == ["warmup"] + ["hard", "jog"] * 6 + ["cooldown"]
    true_ends = [600 + 300 * (i // 2) + (180 if i % 2 == 0 else 300) for i in range(12)]
    assert all(abs(a - b) <= 5 for a, b in zip(_ends(laps)[1:13], true_ends, strict=True))


def test_reps_that_run_long_dont_push_the_later_ones_out_of_line():
    # each rep took 3:20 rather than the planned 3:00, so the plan drifts 20 s a rep
    blocks = [(600, 330, 135)] + [(200, 255, 172), (120, 360, 140)] * 6 + [(600, 345, 135)]
    laps = line_up(
        parse("10 min warm-up, 6 x 3 min hard with 2 min jog, 10 min cool-down"), _session(blocks)
    )
    rep_starts = [lap.start for lap in laps if lap.kind == "hard"]
    assert all(abs(start - (600 + 320 * n)) <= 5 for n, start in enumerate(rep_starts))


def test_distance_steps_use_how_far_the_runner_went():
    series = _session([(600, 330, 135), (1800, 300, 150)])  # 1.8 km, then 6 km at 5:00/km
    laps = line_up(parse("2 km easy, 4 km steady"), series)
    assert [lap.kind for lap in laps] == [
        "steady",
        "steady",
        "steady",
    ]  # the rest of the run follows
    assert abs(laps[0].end - (600 + 60)) <= 15  # 2 km comes a minute after the slower start


def test_steps_beyond_the_end_of_the_run_are_left_out():
    laps = line_up(parse("10 min warm-up, 20 x 3 min hard with 2 min jog"), _session(INTERVALS))
    assert laps[-1].end == len(_session(INTERVALS))
    assert len(laps) < 1 + 2 * 20
    assert len(steps_of(parse("20 x 3 min hard with 2 min jog"))) == 40


def test_a_typed_workout_becomes_the_runs_laps(app, auth_client, user):
    run_id = _interval_run(app, user)
    typed = "10' wu, 6x 3 min hard / 2 min jog, 10' cd"
    page = auth_client.post(
        f"/runs/{run_id}/laps", data={"action": "workout", "workout": typed}, follow_redirects=True
    ).get_data(as_text=True)
    assert "Your workout is lined up with the run: 14 laps." in page
    assert (
        "Lined up from your workout: 10 min warm-up, 6 x (3 min hard, 2 min jog), 10 min cool-down"
        in page
    )
    source, laps = _laps(app, run_id)
    assert source == "manual" and [kind for kind, _, _ in laps][:3] == ["warmup", "hard", "jog"]
    with app.app_context():
        assert db.session.get(Run, run_id).workout.startswith("10 min warm-up")


def test_a_note_is_never_kept_as_the_workout(app, auth_client, user):
    run_id = _interval_run(app, user)
    page = auth_client.post(
        f"/runs/{run_id}/laps",
        data={"action": "workout", "workout": "10 min easy, felt my knee"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "couldn" in page and "felt my knee" in page  # said back to the runner, not stored
    with app.app_context():
        assert db.session.get(Run, run_id).workout is None
