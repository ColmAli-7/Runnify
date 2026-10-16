"""Each song's page: its lift and evidence, a dot per measured play, the trend and its runs."""

from datetime import timedelta

import pytest

from runnify.extensions import db
from runnify.models import Run, Song, User, UserSongHistory, utcnow
from runnify.security.passwords import hash_password
from runnify.services import songs
from runnify.services.insights import Effect
from tests.conftest import PASSWORD, sign_in_as
from tests.factories import make_scored_run

NBSP = "\u00a0"


def _runs(user, count):
    """``count`` runs a week apart ending last week, each with Fast, Slow, Steady and Skipped Song.

    Fast Song lifts the pace by 20 s/km, Slow Song drags it by 20, Steady Song
    changes nothing and Skipped Song plays too briefly to measure (see tests.factories).
    """
    last = utcnow().replace(hour=7, minute=0, second=0, microsecond=0) - timedelta(weeks=1)
    starts = [last - timedelta(weeks=n) for n in reversed(range(count))]
    return [make_scored_run(user, start, f"run-{n}") for n, start in enumerate(starts)]


def _other_runner(app):
    with app.app_context():
        other = User(
            name="Other Runner", email="other@example.com", password_hash=hash_password(PASSWORD)
        )
        other.record_consent()
        db.session.add(other)
        db.session.commit()
        return other.id


def test_a_song_page_shows_its_lift_evidence_chart_and_runs(app, auth_client, user):
    with app.app_context():
        run_ids = _runs(user, 3)
    page = auth_client.get("/songs/fast")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "<h1>Fast Song</h1>" in html and "Test Artist" in html
    assert "<strong>Your strongest song.</strong> It lifts your pace by 12" in html
    assert "All time: 3 runs, 3 measured plays, medium confidence" in html
    assert html.count('class="dot dot--up"') == 3  # one dot per measured play
    assert 'class="trend"' in html and f"The trend line is level at +20{NBSP}s/km." in html
    assert "Compared with the minutes around them, 3 were faster." in html
    for run_id in run_ids:
        assert f'<a href="/runs/{run_id}">' in html
    assert '<a href="/insights" aria-current="page">' in html  # songs live under Insights


def test_another_runners_song_is_not_found(app, auth_client, user):
    other = _other_runner(app)
    with app.app_context():
        make_scored_run(other, activity_id="theirs")
    assert auth_client.get("/songs/fast").status_code == 404  # the song exists, but not for us
    assert auth_client.get("/songs/no-such-song").status_code == 404
    sign_in_as(auth_client, other)
    assert auth_client.get("/songs/fast").status_code == 200


def test_a_song_with_one_measured_play_says_how_much_more_it_needs(app, auth_client, user):
    with app.app_context():
        _runs(user, 1)
    html = auth_client.get("/songs/fast").get_data(as_text=True)
    assert "<strong>Not ranked yet.</strong>" in html
    assert f"Its one measured play was 20{NBSP}s/km faster than the minutes around it." in html
    assert "It needs 1 more measured play before it can rank." in html
    assert "Compared with the minutes around it, 1 was faster." in html
    assert "A trend line appears once it has 3 measured plays on different days." in html


def test_a_song_never_measured_still_has_a_page(app, auth_client, user):
    with app.app_context():
        _runs(user, 1)
    html = auth_client.get("/songs/skipped").get_data(as_text=True)
    assert "You skipped it before it could be measured." in html
    assert "It needs 2 measured plays before it can rank." in html
    assert "Not measured yet" in html and "Nothing to draw yet" in html
    assert '<span class="tag">Skipped</span>' in html


def test_the_record_counts_every_play_and_ranks_the_measured_ones(app, user):
    with app.app_context():
        _runs(user, 3)
        skipped = songs.song_record(user, "skipped")
        assert len(skipped.plays) == 3 and skipped.runs == 3 and skipped.skips == 3
        assert skipped.effect.plays == 0 and skipped.measured == [] and skipped.plays_to_rank == 2

        fast = songs.song_record(user, "fast")
        assert fast.effect.plays == 3 and fast.effect.lift == pytest.approx(20.0)
        assert fast.effect.shrunk_lift == pytest.approx(20.0 * 3 / 5)  # as Insights ranks it
        assert (fast.rank, fast.ranked_songs, fast.plays_to_rank) == (1, 1, 0)
        assert fast.plays[0].run.date_time > fast.plays[-1].run.date_time  # newest first
        assert fast.plays[0].on_at == 480  # it came on eight minutes in
        assert fast.trend.first == pytest.approx(20.0) and not fast.trend.clear

        assert songs.song_record(user, "slow").rank == 1  # the biggest drag
        assert songs.song_record(user, "steady").rank is None  # too small to rank either way
        assert songs.song_record(user, "no-such-song") is None


def test_plays_of_a_song_on_another_runners_runs_are_left_out(app, user):
    other = _other_runner(app)
    with app.app_context():
        mine = make_scored_run(user)
        theirs = db.session.get(Run, make_scored_run(other, activity_id="theirs"))
        # a play stored against someone else's run must never show up on my page
        db.session.add(UserSongHistory(user_id=user, song_id="fast", run_id=theirs.id))
        db.session.commit()
        record = songs.song_record(user, "fast")
        assert [play.run.id for play in record.plays] == [mine]


def test_a_trend_is_only_called_clear_when_it_beats_the_ups_and_downs():
    wobble = [3.0, -3.0, 2.0, -2.0, 3.0, -3.0, 2.0, -2.0, 3.0, -3.0]
    rising = [(week * 7, week * 2.0 + w, 180) for week, w in enumerate(wobble)]
    trend = songs.fit_trend(rising)
    assert trend.per_day == pytest.approx(2.0 / 7, rel=0.2)
    assert trend.clear and trend.last > trend.first
    assert not songs.fit_trend([(week * 7, w, 180) for week, w in enumerate(wobble)]).clear
    assert not songs.fit_trend(rising[:5]).clear  # too few plays to call, however steep
    assert songs.fit_trend(rising[:2]) is None  # too few to draw
    assert songs.fit_trend([(0, 1.0, 180), (0, 5.0, 180), (0, 3.0, 180)]) is None  # one day


def _record(lift, plays, rank=None, ranked_songs=0, trend=None):
    effect = Effect(key="song", label="Song", plays=plays, lift=lift, runs=set(range(plays)))
    return songs.SongRecord(
        song=Song(id="song", name="Song"),
        plays=[],
        effect=effect,
        rank=rank,
        ranked_songs=ranked_songs,
        trend=trend,
    )


@pytest.mark.parametrize(
    ("record", "lead", "text"),
    [
        (
            _record(12.0, 10, rank=1, ranked_songs=3),
            "Your strongest song.",
            f"It lifts your pace by 10{NBSP}s/km across 10 runs.",
        ),
        (
            _record(12.0, 10, rank=2, ranked_songs=3),
            "Your 2nd strongest song.",
            f"It lifts your pace by 10{NBSP}s/km across 10 runs.",
        ),
        (
            _record(4.0, 10, rank=7, ranked_songs=9),
            "A smaller lift.",
            f"It lifts your pace by 3{NBSP}s/km across 10 runs, 7th of the 9 songs that do.",
        ),
        (
            _record(-12.0, 10, rank=1, ranked_songs=2),
            "Your biggest drag.",
            f"It slows you down by 10{NBSP}s/km across 10 runs. Save it for the cool-down.",
        ),
        (
            _record(-4.0, 10, rank=6, ranked_songs=6),
            "A smaller drag.",
            f"It slows you down by 3{NBSP}s/km across 10 runs, 6th of the 6 songs that do.",
        ),
        (
            _record(0.5, 10),
            "Little effect on your pace.",
            f"Its lift is under 1{NBSP}s/km either way across 10 runs.",
        ),
        (
            _record(-30.0, 1),
            "Not ranked yet.",
            f"Its one measured play was 30{NBSP}s/km slower than the minutes around it."
            " It needs 1 more measured play before it can rank.",
        ),
        (
            _record(12.0, 10, rank=1, ranked_songs=3, trend=songs.Trend(4.0, 13.0, 0.1, True)),
            "Your strongest song.",
            f"It lifts your pace by 10{NBSP}s/km across 10 runs."
            f" Its lift has risen on recent runs, from +4 to +13{NBSP}s/km.",
        ),
    ],
)
def test_the_sentence_is_worked_out_from_the_numbers(record, lead, text):
    verdict = songs.verdict(record)
    assert (verdict.lead, verdict.text) == (lead, text)


def test_the_trend_note_says_whether_the_line_is_more_than_chance():
    unclear = _record(12.0, 10, rank=1, trend=songs.Trend(4.0, 9.0, 0.05, False))
    assert songs.trend_note(unclear) == (
        f"The trend line rises from +4 to +9{NBSP}s/km,"
        " but its plays vary too much to call that a trend yet."
    )
    clear = _record(-12.0, 10, rank=1, trend=songs.Trend(-6.0, -18.0, -0.1, True))
    assert songs.trend_note(clear) == (
        f"The trend line falls from \u22126 to \u221218{NBSP}s/km,"
        " more than the ups and downs of its plays would explain."
    )
