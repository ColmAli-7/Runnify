"""A run's results sheet, built from its stream and stored song effects."""

import pytest

from runnify.extensions import db
from runnify.models import Run
from runnify.services.results import run_results, run_summaries
from tests.factories import make_scored_run


@pytest.fixture
def scored_run(app, user):
    with app.app_context():
        return make_scored_run(user)


def test_songs_are_ranked_by_their_lift(app, scored_run):
    with app.app_context():
        results = run_results(db.session.get(Run, scored_run))
        assert [row.song.id for row in results.rows] == ["steady", "fast", "slow", "skipped"]
        assert [row.song.id for row in results.ranked] == ["fast", "steady", "slow"]
        assert [row.position for row in results.ranked] == [1, 2, 3]
        assert results.best.song.id == "fast" and results.best.lift == pytest.approx(20.0, abs=1)
        assert results.worst.song.id == "slow" and results.worst.lift == pytest.approx(-20.0, abs=1)
        assert results.rows[1].start == 480 and results.rows[1].seconds == 180


def test_unscored_plays_say_why(app, scored_run):
    with app.app_context():
        (skipped,) = run_results(db.session.get(Run, scored_run)).unscored
        assert skipped.song.id == "skipped" and skipped.note == "Skipped"


def test_bands_follow_the_playing_order(app, scored_run):
    with app.app_context():
        bands = run_results(db.session.get(Run, scored_run)).bands()
        assert bands[1] == (480, 660, "Fast Song", "best")
        assert bands[2][3] == "worst"


def test_a_run_without_a_stream_has_no_rows(app, user):
    with app.app_context():
        run = Run(user_id=user, activity_id="bare", distance=5000, duration=1500)
        db.session.add(run)
        db.session.commit()
        results = run_results(run)
        assert results.rows == [] and results.best is None


def test_summaries_count_songs_and_find_the_best(app, scored_run):
    with app.app_context():
        summary = run_summaries([scored_run])[scored_run]
        assert summary.songs == 4
        assert summary.best.id == "fast" and summary.best_lift == pytest.approx(20.0, abs=1)
        assert run_summaries([]) == {}
