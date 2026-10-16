"""The demo seed: realistic data that the real pipeline must make sense of."""

import pytest

from runnify import create_app
from runnify.extensions import db
from runnify.models import Playlist, Run, RunSongAnalysis, User, UserSongHistory
from runnify.services import insights, songs
from runnify.services.demo import DEMO_EMAIL, DemoError, seed
from tests.test_config import SafeProductionConfig


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """Seed once: simulating 36 runs second by second takes a moment."""
    from runnify.config import TestConfig

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        seed(app, "demo password for tests")
        yield app


def test_seed_creates_a_complete_account(demo):
    user = User.query.filter_by(email=DEMO_EMAIL).one()
    assert Run.query.filter_by(user_id=user.id).count() == 36
    assert RunSongAnalysis.query.filter_by(user_id=user.id).count() > 300
    assert len(user.friends) == 3
    assert Playlist.query.filter_by(user_id=user.id).count() == 1


def test_the_pipeline_recovers_the_hidden_song_effects(demo):
    user = User.query.filter_by(email=DEMO_EMAIL).one()
    result = insights.overview(user.id, "all")
    boosters = {s.label for s in result.power_songs}
    draggers = {s.label for s in result.drag_songs}
    assert boosters & {"Can't Hold Us", "Mr. Brightside", "Till I Collapse", "Lose Yourself"}
    assert draggers & {"Hallelujah", "Holocene", "The Night We Met", "Skinny Love"}


def test_insights_counts_skips_as_each_song_page_does(demo):
    user = User.query.filter_by(email=DEMO_EMAIL).one()
    counts = {count.key: count for count in insights.skip_counts(user.id)}  # all time
    heard = {play.song_id for play in UserSongHistory.query.filter_by(user_id=user.id)}
    assert set(counts) == heard  # every song the demo runner heard
    for song_id, count in counts.items():
        record = songs.song_record(user.id, song_id)
        page = (record.skips, len(record.plays), record.runs)
        assert (count.skips, count.heard, len(count.runs)) == page, record.name


def test_seeding_twice_replaces_the_demo(demo):
    seed(demo, "another password")
    assert User.query.filter_by(email=DEMO_EMAIL).count() == 1


def test_never_in_production():
    with pytest.raises(DemoError):
        seed(create_app(SafeProductionConfig), "x")
