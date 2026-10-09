"""The dashboard's setup progress, totals and weekly distance, and pages with real data."""

from datetime import datetime

import pytest

from runnify.extensions import db
from runnify.models import Run, User
from runnify.services import dashboard
from tests.factories import make_scored_run


def test_setup_follows_what_is_stored(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        fresh = dashboard.setup_state(account)
        assert not (fresh.has_runs or fresh.has_music or fresh.has_results or fresh.complete)
        make_scored_run(user)
        done = dashboard.setup_state(account)
        assert done.has_runs and done.has_music and done.has_results and done.complete
        assert not done.garmin_linked and not done.spotify_linked


def test_totals(app, user):
    with app.app_context():
        db.session.add_all(
            [
                Run(
                    user_id=user,
                    activity_id="a",
                    date_time=datetime(2026, 9, 1),
                    distance=5000,
                    duration=1500,
                ),
                Run(
                    user_id=user,
                    activity_id="b",
                    date_time=datetime(2026, 10, 1),
                    distance=10000,
                    duration=3000,
                ),
            ]
        )
        db.session.commit()
        everything = dashboard.totals(user)
        assert (everything.runs, everything.metres, everything.seconds) == (2, 15000.0, 4500)
        assert everything.pace == pytest.approx(300.0)
        assert dashboard.totals(user, since=datetime(2026, 9, 15)).runs == 1
        assert dashboard.totals(999).pace is None


def test_weekly_distance_runs_monday_to_sunday(app, user):
    with app.app_context():
        db.session.add_all(
            [
                Run(
                    user_id=user,
                    activity_id="sun",
                    date_time=datetime(2026, 10, 4, 9),
                    distance=3000,
                ),
                Run(
                    user_id=user,
                    activity_id="mon",
                    date_time=datetime(2026, 10, 5, 7),
                    distance=5000,
                ),
                Run(
                    user_id=user,
                    activity_id="old",
                    date_time=datetime(2026, 8, 1, 7),
                    distance=9000,
                ),
            ]
        )
        db.session.commit()
        weeks = dashboard.weekly_distance(user, weeks=3, now=datetime(2026, 10, 7, 12))
        assert weeks == [
            (datetime(2026, 9, 21), 0.0),
            (datetime(2026, 9, 28), 3000.0),
            (datetime(2026, 10, 5), 5000.0),
        ]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/dashboard", "Fast Song"),  # the latest run's results
        ("/runs", "Fast Song"),  # the run's best song
        ("/runs?music=1", "Fast Song"),
        ("/insights?range=all", "3 song plays measured across 1 run"),
        ("/playlists", "Build a playlist"),
    ],
)
def test_pages_render_with_real_data(app, auth_client, user, path, expected):
    with app.app_context():
        make_scored_run(user)
    page = auth_client.get(path)
    assert page.status_code == 200
    assert expected in page.get_data(as_text=True)


def test_a_run_page_shows_its_results(app, auth_client, user):
    with app.app_context():
        run_id = make_scored_run(user)
    page = auth_client.get(f"/runs/{run_id}").get_data(as_text=True)
    assert "Fast Song" in page and "Skipped" in page and 'id="timeline-data"' in page
    assert auth_client.get("/runs/999999").status_code == 404
