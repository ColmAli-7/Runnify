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


def _laps(app, run_id):
    with app.app_context():
        run = db.session.get(Run, run_id)
        return run.laps_source, [(lap.kind, lap.start_second, lap.end_second) for lap in run.laps]


def _kinds(app, run_id):
    return [kind for kind, _, _ in _laps(app, run_id)[1]]


def test_the_kind_of_run_can_be_set_and_handed_back(app, auth_client, user):
    run_id = _interval_run(app, user)
    response = auth_client.post(f"/runs/{run_id}/laps", data={"action": "type", "run_type": "race"})
    assert response.headers["Location"] == f"/runs/{run_id}#laps"
    with app.app_context():
        run = db.session.get(Run, run_id)
        assert (run.run_type, run.run_type_manual) == ("race", True)
    auth_client.post(f"/runs/{run_id}/laps", data={"action": "type", "run_type": "auto"})
    with app.app_context():
        run = db.session.get(Run, run_id)
        assert (run.run_type, run.run_type_manual) == ("intervals", False)


def test_laps_can_be_renamed_joined_split_and_worked_out_again(app, auth_client, user):
    run_id = _interval_run(app, user)
    kinds = _kinds(app, run_id)
    renamed = ["steady" if kind == "jog" else kind for kind in kinds]
    auth_client.post(f"/runs/{run_id}/laps", data={"action": "kinds", "kind": renamed})
    source, laps = _laps(app, run_id)
    assert source == "manual" and [kind for kind, _, _ in laps] == renamed

    auth_client.post(f"/runs/{run_id}/laps", data={"action": "merge-1", "kind": renamed})
    joined = _kinds(app, run_id)
    assert len(joined) == len(kinds) - 1 and joined[1] == "hard"  # rep 1 swallowed its recovery

    auth_client.post(f"/runs/{run_id}/laps", data={"action": "split", "split_at": "5:00"})
    _, laps = _laps(app, run_id)
    assert laps[:2] == [("warmup", 0, 300), ("warmup", 300, 600)]

    auth_client.post(f"/runs/{run_id}/laps", data={"action": "reset"})
    assert _laps(app, run_id) == ("detected", _laps(app, _interval_run(app, user, "again"))[1])


def test_changes_that_dont_fit_are_refused_plainly(app, auth_client, user):
    run_id = _interval_run(app, user)
    before = _laps(app, run_id)
    for data, message in [
        ({"action": "split", "split_at": "soon"}, "like 12:30"),
        ({"action": "split", "split_at": "0:05"}, "at least 10 seconds"),
        ({"action": "kinds", "kind": ["hard"]}, "have changed since the page loaded"),
        ({"action": "kinds", "kind": ["sprint"] * len(before[1])}, "Pick a kind for every lap"),
        ({"action": "merge-99", "kind": [k for k, _, _ in before[1]]}, "have changed"),
        ({"action": "type", "run_type": "marathon"}, "Not a valid choice"),
        ({"action": "explode"}, "one Runnify knows how to make"),
    ]:
        page = auth_client.post(f"/runs/{run_id}/laps", data=data, follow_redirects=True)
        assert message in page.get_data(as_text=True), data
    assert _laps(app, run_id) == before


def test_only_your_own_runs_can_be_changed(app, auth_client, user):
    from tests.test_songs import _other_runner

    other = _other_runner(app)
    theirs = _interval_run(app, other, "theirs")
    response = auth_client.post(f"/runs/{theirs}/laps", data={"action": "reset"})
    assert response.status_code == 404
    assert auth_client.get(f"/runs/{theirs}/laps").status_code == 404


def test_the_laps_address_returns_to_the_run(app, auth_client, user):
    run_id = _interval_run(app, user)
    response = auth_client.get(f"/runs/{run_id}/laps")
    assert response.status_code == 302 and response.headers["Location"] == f"/runs/{run_id}#laps"


def test_a_change_without_a_csrf_token_goes_back_to_the_run(tmp_path, monkeypatch):
    from runnify import create_app
    from runnify.models import User
    from tests.conftest import sign_in_as
    from tests.test_csrf import CSRFConfig

    monkeypatch.chdir(tmp_path)
    strict = create_app(CSRFConfig)  # its own database, with CSRF checks on
    with strict.app_context():
        db.create_all()
        runner = User(name="Runner", email="csrf@example.com", password_hash="unused")
        runner.record_consent()
        db.session.add(runner)
        db.session.commit()
        runner_id = runner.id
    run_id = _interval_run(strict, runner_id)
    client = strict.test_client()
    sign_in_as(client, runner_id)
    response = client.post(f"/runs/{run_id}/laps", data={"action": "reset"})
    # back to the laps address, which returns to the run rather than the home page
    assert response.status_code == 303 and response.headers["Location"] == f"/runs/{run_id}/laps"


def test_the_run_page_offers_each_change(app, auth_client, user):
    run_id = _interval_run(app, user)
    html = auth_client.get(f"/runs/{run_id}").get_data(as_text=True)
    assert "Change the laps or the kind of run" in html
    assert html.count('name="csrf_token"') >= 3
    for action in ('value="type"', 'value="kinds"', 'value="merge-0"', 'value="split"'):
        assert action in html
    assert 'value="reset"' not in html  # nothing set by hand yet
