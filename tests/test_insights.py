"""Findings across songs and runs."""

from datetime import datetime, timedelta

import pytest

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, User, UserSongHistory, utcnow
from runnify.services import insights
from tests.factories import make_scored_run


def _heard(user, run, song, seconds=12, skipped=True):
    """A play with no measured effect, by default a skip too short to measure."""
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
    return play


def _play(user, run, song, lift, seconds=180, position=0.5, hr=None, skipped=None, lap=None):
    play = _heard(user, run, song, seconds, skipped)
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
            lap_kind=lap,
            method_version=3,
        )
    )


@pytest.fixture
def seeded(app, user):
    """Four recent runs and one old one, with songs of known effect.

    Some skips came too soon to measure, so they have no effect stored.
    """
    with app.app_context():
        db.session.add_all(
            [
                Song(id="boost", name="Boost", artist="Alpha"),
                Song(id="drag", name="Drag", artist="Beta"),
                Song(id="once", name="Once", artist="Alpha"),
                Song(id="flick", name="Flick", artist="Gamma"),
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
        _heard(user, runs[0], "drag")  # back on later in the run and skipped at once
        _heard(user, runs[2], "boost")  # its only skip, too short to measure
        _heard(user, runs[1], "flick")  # never measured at all
        _heard(user, runs[4], "flick")
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


def test_heart_raisers(app, seeded):
    with app.app_context():
        assert [s.key for s in insights.overview(seeded, "90d").heart_raisers] == ["boost"]


def test_skips_count_every_play_even_one_too_short_to_measure(app, seeded):
    with app.app_context():
        recent = insights.overview(seeded, "90d")
        assert [(s.key, s.skips, s.heard, len(s.runs)) for s in recent.most_skipped] == [
            ("drag", 5, 5, 4),  # four measured skips and one a few seconds in
            ("boost", 1, 5, 4),  # its only skip was too short to measure
            ("flick", 1, 1, 1),  # never measured at all
        ]
        assert recent.power_songs[0].plays == 4  # its lift still rests on measured plays only
        everything = insights.overview(seeded, "all").most_skipped
        assert [(s.key, s.skips, s.heard) for s in everything] == [
            ("drag", 5, 5),
            ("flick", 2, 2),  # its skip a year ago counts on all time only
            ("boost", 1, 6),
        ]


def test_the_most_skipped_highlight_counts_every_play(app, seeded):
    with app.app_context():
        found = {h.kicker: h for h in insights.highlights(insights.overview(seeded, "90d"))}
        skipped = found["Most skipped"]
        assert (skipped.lead, skipped.figure, skipped.unit, skipped.foot) == (
            "Drag",
            "5",
            "of 5 plays",
            "4 runs",
        )


def test_insights_and_the_song_page_agree_on_a_skip_too_short_to_measure(app, auth_client, user):
    """Through the real pipeline: Skipped Song plays for 10 seconds, too briefly to measure."""
    with app.app_context():
        for weeks in (1, 2):
            make_scored_run(user, utcnow() - timedelta(weeks=weeks), f"run-{weeks}")
    page = auth_client.get("/insights").get_data(as_text=True)
    assert '<span class="ranks__name"><a href="/songs/skipped">Skipped Song</a>' in page
    assert '<span class="ranks__figure">2 of 2 plays</span>' in page
    assert '<p class="highlight__figure">2<span class="highlight__unit">of 2 plays</span>' in page
    song_page = auth_client.get("/songs/skipped").get_data(as_text=True)
    assert (
        '<span class="stat__value">2</span><span class="stat__unit">of 2 plays</span>' in song_page
    )


def test_skips_on_another_runners_runs_are_left_out(app, seeded):
    with app.app_context():
        other = User(name="Other Runner", email="other@example.com", password_hash="unused")
        db.session.add(other)
        db.session.flush()
        theirs = Run(
            user_id=other.id, activity_id="theirs", date_time=utcnow(), duration=1500, distance=5000
        )
        db.session.add(theirs)
        db.session.flush()
        _heard(other.id, theirs, "flick")  # their own skip
        _heard(seeded, theirs, "flick")  # a play stored against someone else's run
        db.session.commit()
        flick = next(s for s in insights.overview(seeded, "all").most_skipped if s.key == "flick")
        assert (flick.skips, flick.heard) == (2, 2)  # only the two on my own runs


def test_highlights_about_a_song_carry_its_id(app, seeded):
    with app.app_context():
        found = {h.kicker: h.song_id for h in insights.highlights(insights.overview(seeded, "90d"))}
        assert (found["Power song"], found["Drag song"]) == ("boost", "drag")
        assert (found["Heart raiser"], found["Most skipped"]) == ("boost", "drag")
        assert found["With music"] is None  # not about one song


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


@pytest.fixture
def intervals(app, seeded):
    """On top of ``seeded``'s steady running: two interval runs, where "rep" lifts the reps and
    "float" helps only the jogs between them."""
    with app.app_context():
        db.session.add_all(
            [
                Song(id="rep", name="Rep", artist="Delta"),
                Song(id="float", name="Float", artist="Delta"),
            ]
        )
        for days_ago in (2, 4):
            run = Run(
                user_id=seeded,
                activity_id=f"intervals{days_ago}",
                date_time=utcnow() - timedelta(days=days_ago),
                duration=2400,
                distance=8000,
                run_type="intervals",
            )
            db.session.add(run)
            db.session.flush()
            _play(seeded, run, "rep", 9.0, lap="hard")
            _play(seeded, run, "float", 6.0, lap="jog")
            _play(seeded, run, "boost", -3.0, lap="hard")  # lifts steady running, not reps
        db.session.commit()
    return seeded


def test_findings_narrow_to_one_kind_of_running(app, intervals):
    with app.app_context():
        everything = insights.overview(intervals, "90d")
        assert everything.all_running and everything.plays == 15
        hard = insights.overview(intervals, "90d", "hard")
        assert (hard.kind, hard.kind_label, hard.plays) == ("hard", "Hard efforts", 4)
        assert [s.key for s in hard.power_songs] == ["rep"]
        assert [s.key for s in hard.drag_songs] == ["boost"]
        recoveries = insights.overview(intervals, "90d", "recoveries")
        assert [s.key for s in recoveries.power_songs] == ["float"]
        # skips and whole runs have no one kind of lap: they stay across all running
        assert [s.key for s in hard.most_skipped] == [s.key for s in everything.most_skipped]
        kickers = {h.kicker for h in insights.highlights(hard)}
        assert "Power song" in kickers and not kickers & {"Most skipped", "With music"}
        assert insights.overview(intervals, "90d", "sideways").all_running  # unknown: all running


def test_the_page_offers_each_kind_of_running_and_keeps_the_range(app, auth_client, intervals):
    html = auth_client.get("/insights?range=all&kind=hard").get_data(as_text=True)
    assert 'href="/insights?range=all&amp;kind=hard" aria-current="true">Hard efforts</a>' in html
    assert 'href="/insights?range=30d&amp;kind=hard">Last 30 days</a>' in html
    assert 'href="/insights?range=all">All running</a>' in html
    assert "4 song plays measured on hard efforts across 2 runs, all time." in html
    assert "Across all running" in html  # most skipped


def test_a_kind_with_nothing_measured_says_so(app, auth_client, seeded):
    html = auth_client.get("/insights?kind=recoveries").get_data(as_text=True)
    assert "Nothing measured on recoveries in this period" in html
    assert 'href="/insights?range=90d">See all running</a>' in html
