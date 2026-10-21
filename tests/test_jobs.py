"""Background jobs: progress, interruptions and the JSON the pages poll."""

import io
import os
import pathlib
import time
from datetime import timedelta

import pytest

from runnify.extensions import db
from runnify.models import User, utcnow
from runnify.services import garmin as garmin_service
from runnify.services import imports, jobs


def _set(app, user_id, **fields):
    with app.app_context():
        account = db.session.get(User, user_id)
        for name, value in fields.items():
            setattr(account, name, value)
        db.session.commit()


def _job(app, user_id, kind):
    with app.app_context():
        return jobs.job(db.session.get(User, user_id), kind)


def test_a_job_that_never_ran_has_no_state(app, user):
    assert _job(app, user, "garmin") == jobs.Job("garmin", None, None)


def test_a_job_reporting_recently_is_running(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        jobs.begin(account, "history", "Starting the import")
        db.session.commit()
    job = _job(app, user, "history")
    assert job.running and job.message == "Starting the import" and job.percent is None


@pytest.mark.parametrize("silent", [None, jobs.STALE_AFTER + timedelta(seconds=1)])
def test_a_job_silent_too_long_was_interrupted(app, user, silent):
    reported = None if silent is None else utcnow() - silent
    _set(app, user, garmin_sync_state="syncing", garmin_sync_updated_at=reported)
    job = _job(app, user, "garmin")
    assert job.state == "interrupted" and not job.running


def test_progress_is_written_at_most_once_a_second(app, user):
    with app.app_context():
        progress = jobs.Progress(user, "history", every=60)
        assert progress.report("Scoring the songs on your runs: 1 of 4", 1, 4)
        assert not progress.report("Scoring the songs on your runs: 2 of 4", 2, 4)
        assert progress.report("Scoring the songs on your runs: 3 of 4", 3, 4, force=True)
    job = _job(app, user, "history")
    assert (job.message, job.percent) == ("Scoring the songs on your runs: 3 of 4", 75)


def test_finishing_clears_the_progress(app, user):
    with app.app_context():
        jobs.Progress(user, "garmin").report("Bringing in your runs", 3, 10)
        jobs.end(db.session.get(User, user), "garmin", "ok", "3 new runs imported.")
        db.session.commit()
    assert _job(app, user, "garmin") == jobs.Job("garmin", "ok", "3 new runs imported.")


def test_the_status_is_served_as_json(app, auth_client, user):
    with app.app_context():
        jobs.Progress(user, "history").report("Reading your listening history: 40%", 40, 100)
    response = auth_client.get("/jobs")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["history"] == {
        "kind": "history",
        "state": "running",
        "running": True,
        "message": "Reading your listening history: 40%",
        "done": 40,
        "total": 100,
        "percent": 40,
    }
    assert response.json["garmin"]["state"] is None


def test_the_status_needs_a_sign_in(client):
    assert client.get("/jobs").status_code == 302


def test_a_running_sync_refuses_another_but_an_interrupted_one_restarts(
    app, auth_client, user, monkeypatch
):
    started = []
    monkeypatch.setattr(garmin_service, "start_background_sync", lambda a, uid: started.append(uid))
    _set(
        app, user, garmin_tokens="{}", garmin_sync_state="syncing", garmin_sync_updated_at=utcnow()
    )
    page = auth_client.post("/connections/garmin/sync", follow_redirects=True)
    assert b"A sync is already running" in page.data and started == []
    _set(app, user, garmin_sync_updated_at=utcnow() - timedelta(hours=1))
    page = auth_client.get("/connections")
    assert b"The last sync stopped before it finished" in page.data
    auth_client.post("/connections/garmin/sync")
    assert started == [user]


def test_an_interrupted_import_says_so_and_takes_a_new_upload(app, auth_client, user):
    _set(app, user, history_import_state="importing", history_import_updated_at=None)
    page = auth_client.get("/import")
    assert b"Interrupted" in page.data and b"stopped before it finished" in page.data
    assert b'type="submit" disabled' not in page.data


def test_the_import_page_shows_how_far_a_running_import_has_got(app, auth_client, user):
    with app.app_context():
        jobs.Progress(user, "history").report("Scoring the songs on your runs: 3 of 12", 3, 12)
    page = auth_client.get("/import").get_data(as_text=True)
    assert "Scoring the songs on your runs: 3 of 12" in page
    assert 'value="25"' in page and 'data-job="history"' in page


def test_uploads_an_interrupted_import_left_behind_are_swept(app, tmp_path):
    folder = pathlib.Path(app.config["UPLOAD_TMP_DIR"])
    folder.mkdir(parents=True)
    old, recent = folder / "old.zip", folder / "recent.zip"
    old.write_bytes(b"x")
    recent.write_bytes(b"x")
    long_ago = time.time() - imports.LEFT_BEHIND - 60
    os.utime(old, (long_ago, long_ago))
    imports._sweep(folder)
    assert not old.exists() and recent.exists()


def test_a_running_job_has_a_notice_on_other_pages_only(app, auth_client, user):
    with app.app_context():
        jobs.Progress(user, "garmin").report("Bringing in your runs: 4 new so far")
        jobs.Progress(user, "history").report("Reading your listening history: 10%", 10, 100)
    dashboard = auth_client.get("/dashboard").get_data(as_text=True)
    assert 'data-job-notice="garmin"' in dashboard and 'data-job-notice="history"' in dashboard
    assert "Bringing in your runs: 4 new so far" in dashboard and "js/jobs.js" in dashboard
    upload_page = auth_client.get("/import").get_data(as_text=True)
    assert 'data-job-notice="garmin"' in upload_page
    assert 'data-job-notice="history"' not in upload_page  # the page shows it in full
    connections = auth_client.get("/connections").get_data(as_text=True)
    assert (
        "data-job-notice" not in connections and 'data-job-reload="garmin history"' in connections
    )


def test_no_notice_once_a_job_has_ended(app, auth_client, user):
    _set(app, user, garmin_sync_state="ok", garmin_sync_message="2 new runs imported.")
    assert b"data-job-notice" not in auth_client.get("/dashboard").data


def test_scripted_uploads_learn_where_to_go(app, auth_client, user):
    response = auth_client.post(
        "/import",
        data={"history_zip": (io.BytesIO(b"x"), "history.json")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200 and response.json == {"location": "/import"}
    assert b"Choose the .zip file" in auth_client.get("/import").data  # the message waits there
