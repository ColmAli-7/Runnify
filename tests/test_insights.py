"""Findings across songs and runs."""

from datetime import datetime, timedelta

import pytest

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory, utcnow
from runnify.services import insights


def _play(user, run, song, lift, seconds=180, position=0.5, hr=None, skipped=None):
    play = UserSongHistory(
        user_id=user,
        song_id=song,
        run_id=run.id,
        played_at=run.date_time,
        time_played=seconds,
        skipped=skipped,
    )
    db.session.add(play)
    db.session.flush()
    db.session.add(
        RunSongAnalysis(
            run_id=run.id,
            user_song_id=play.id,
            user_id=user,
            performance_score=50 + lift,
            pace_delta=lift,
            hr_delta=hr,
            seconds=seconds,
            position=position,
            method_version=2,
        )
    )


@pytest.fixture
def seeded(app, user):
    """Four recent runs and one old one, with songs of known effect."""
    with app.app_context():
        db.session.add_all(
            [
                Song(id="boost", name="Boost", artist="Alpha"),
                Song(id="drag", name="Drag", artist="Beta"),
                Song(id="once", name="Once", artist="Alpha"),
            ]
        )
        now = utcnow()
        runs = []
        for days_ago in (1, 3, 5, 7, 400):
            run = Run(
                user_id=user,
                activity_id=str(days_ago),
                date_time=now - timedelta(days=days_ago),
                duration=1500,
                distance=5000,
            )
            db.session.add(run)
            runs.append(run)
        silent = Run(
            user_id=user,
            activity_id="silent",
            date_time=now - timedelta(days=2),
            duration=1800,
            distance=5000,
        )
        db.session.add(silent)
        db.session.flush()
        for run in runs[:4]:
            _play(user, run, "boost", 12.0, position=0.9, hr=6.0)
            _play(user, run, "drag", -8.0, position=0.1, skipped=True)
        _play(user, runs[0], "once", 30.0)  # one lucky play
        _play(user, runs[4], "boost", -50.0)  # a year ago: outside the 90-day range
        db.session.commit()
    return user


def test_rankings_need_repeated_evidence(app, seeded):
    with app.app_context():
        result = insights.overview(seeded, "90d")
        assert [s.key for s in result.power_songs] == ["boost"]  # "once" has one play only
        assert [s.key for s in result.drag_songs] == ["drag"]
        boost = result.power_songs[0]
        assert boost.plays == 4 and boost.confidence == "medium"
        assert boost.lift == pytest.approx(12.0)
        assert boost.shrunk_lift == pytest.approx(12.0 * 4 / 6)  # shrunk by two neutral plays


def test_phases_average_the_songs_in_each_part_of_a_run(app, seeded):
    with app.app_context():
        phases = {p.label: p for p in insights.overview(seeded, "90d").phases}
        assert phases["Finish"].lift == pytest.approx(12.0)
        assert phases["Start"].lift == pytest.approx(-8.0)
        assert phases["Finish"].strength is None  # too few plays to judge


def _plays(position, factor, shift=0.0, runs=8):
    """Songs with usual effects of +8, +4, -4 and -8 s/km, scaled by ``factor`` here."""
    usual = {"a": 8.0, "b": 4.0, "c": -4.0, "d": -8.0}
    return [
        (key, position, value * factor + shift, 180)
        for _ in range(runs)
        for key, value in usual.items()
    ]


def test_strength_shows_where_songs_work_hardest():
    start, middle, finish = insights.phase_summary(
        _plays(0.05, 0.5) + _plays(0.5, 1.0) + _plays(0.9, 1.5)
    )
    assert (start.label, middle.label, finish.label) == ("Start", "Middle", "Finish")
    assert middle.strength == pytest.approx(1.0)
    assert start.strength < 0.6 and finish.strength > 1.4  # half as strong, and half as much again


def test_strength_ignores_a_shift_that_hits_every_song():
    steady = insights.phase_summary(_plays(0.05, 1.0) + _plays(0.5, 1.0))
    warm_up = insights.phase_summary(_plays(0.05, 1.0, shift=-10.0) + _plays(0.5, 1.0))
    assert warm_up[0].lift == pytest.approx(steady[0].lift - 10.0)
    assert warm_up[0].strength == pytest.approx(steady[0].strength, rel=0.02)


def test_strength_needs_repeated_songs():
    once_each = [(f"song{i}", 0.5, float(i), 180) for i in range(20)]
    assert insights.phase_summary(once_each)[1].strength is None


def test_heart_rate_and_skips(app, seeded):
    with app.app_context():
        result = insights.overview(seeded, "90d")
        assert [s.key for s in result.heart_raisers] == ["boost"]
        assert result.most_skipped[0].key == "drag" and result.most_skipped[0].skips == 4


def test_runs_with_and_without_music_are_compared(app, seeded):
    with app.app_context():
        result = insights.overview(seeded, "90d")
        assert result.with_music_pace == pytest.approx(300.0)
        assert result.without_music_pace == pytest.approx(360.0)


def test_ranges_filter_by_run_date(app, seeded):
    with app.app_context():
        recent = insights.overview(seeded, "90d")
        everything = insights.overview(seeded, "all")
        assert recent.plays == 9 and everything.plays == 10
        assert insights.overview(seeded, "nonsense").range_key == insights.DEFAULT_RANGE


def test_no_data(app, user):
    with app.app_context():
        result = insights.overview(user)
        assert not result.has_data and result.power_songs == []


def test_confidence_levels():
    assert [insights.confidence(n) for n in (1, 2, 4, 5)] == ["low", "medium", "medium", "high"]


def test_year_range_starts_on_january_first():
    assert insights.range_start("year", now=datetime(2026, 10, 9)) == datetime(2026, 1, 1)
