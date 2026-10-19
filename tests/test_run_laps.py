"""A run's laps and type on its page and in the runs list."""

from runnify.extensions import db
from runnify.models import Run
from runnify.services.laps import refresh_laps
from runnify.services.streams import save_stream
from tests.factories import make_scored_run
from tests.test_laps import INTERVALS, _session


def _interval_run(app, user, activity_id="intervals"):
    """A 50-minute interval session with its laps worked out, as a sync would leave it."""
    with app.app_context():
        series = _session(INTERVALS)
        run = Run(
            user_id=user,
            activity_id=activity_id,
            date_time=series.timestamps[0],
            duration=len(series),
            distance=9000,
        )
        db.session.add(run)
        db.session.flush()
        save_stream(run, series)
        refresh_laps(run, series)
        db.session.commit()
        return run.id


def test_a_run_page_shows_its_laps_and_kind_of_run(app, auth_client, user):
    run_id = _interval_run(app, user)
    html = auth_client.get(f"/runs/{run_id}").get_data(as_text=True)
    assert '<span class="tag run__type">Intervals</span>' in html
    assert "Worked out from your pace and heart rate" in html
    assert html.count('class="lane__block lane__block--hard"') == 6  # one block per rep
    assert html.count('<span class="rank">') >= 13  # a row per lap in the lap table
    assert (
        '<span class="legend__swatch legend__swatch--lap-warmup" aria-hidden="true"></span>Warm-up'
        in html
    )
    assert "measured against your other reps" in html


def test_a_steady_run_is_one_stretch_with_no_lane(app, auth_client, user):
    with app.app_context():
        run_id = make_scored_run(user)
    html = auth_client.get(f"/runs/{run_id}").get_data(as_text=True)
    assert "One steady stretch from start to finish" in html
    assert "lane--laps" not in html
    assert '<span class="tag">Steady</span>' not in html  # songs aren't tagged on a steady run


def test_the_runs_list_names_sessions_but_not_easy_runs(app, auth_client, user):
    _interval_run(app, user)
    with app.app_context():
        make_scored_run(user, activity_id="easy")
    html = auth_client.get("/runs").get_data(as_text=True)
    assert '<span class="tag">Intervals</span>' in html
    assert "Easy run</span>" not in html
