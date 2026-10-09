"""Garmin linking and sync, with a fake Garmin client."""

import io
import json
import pathlib
import zipfile

import pytest

from runnify.extensions import db
from runnify.models import Run, User
from runnify.services import garmin as garmin_service

TOKENS = json.dumps({"di_token": "t", "di_refresh_token": "r", "di_client_id": "c"})


def _fit_zip(name="123_ACTIVITY.fit"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, b"FAKEFIT")
    return buffer.getvalue()


class FakeTokens:
    def dumps(self):
        return TOKENS


class FakeGarmin:
    """Stands in for ``garminconnect.Garmin``: one run and one swim."""

    ActivityDownloadFormat = garmin_service.Garmin.ActivityDownloadFormat
    needs_mfa = False
    instances = []

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.username, self.password = email, password
        self.client = FakeTokens()
        self.tokenstore = None
        FakeGarmin.instances.append(self)

    def login(self, tokenstore=None):
        self.tokenstore = tokenstore
        if tokenstore is None and self.password != "garmin-secret":
            raise garmin_service.GarminConnectAuthenticationError("bad credentials")
        return ("needs_mfa", None) if self.needs_mfa else (None, None)

    def resume_login(self, state, code):
        if code != "123456":
            raise garmin_service.GarminConnectAuthenticationError("bad code")
        return None, None

    def get_activities(self, start, limit):
        if start:
            return []
        common = {"startTimeGMT": "2026-10-01 07:00:00", "duration": 1800.0, "distance": 5000.0}
        return [
            {
                "activityId": 123,
                "activityType": {"typeKey": "running"},
                "averageSpeed": 2.78,
                **common,
            },
            {"activityId": 456, "activityType": {"typeKey": "lap_swimming"}, **common},
        ]

    def download_activity(self, activity_id, dl_fmt=None):
        return _fit_zip()


@pytest.fixture(autouse=True)
def fake_garmin(monkeypatch):
    FakeGarmin.needs_mfa = False
    FakeGarmin.instances = []
    monkeypatch.setattr(garmin_service, "Garmin", FakeGarmin)
    return FakeGarmin


@pytest.fixture
def syncs(monkeypatch):
    """Record background syncs instead of starting threads."""
    started = []
    monkeypatch.setattr(
        garmin_service, "start_background_sync", lambda app, uid: started.append(uid)
    )
    return started


def _set(app, user_id, **fields):
    with app.app_context():
        account = db.session.get(User, user_id)
        for name, value in fields.items():
            setattr(account, name, value)
        db.session.commit()


def test_sync_from_tokens_saves_runs_and_fit_files(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        added = garmin_service.fetch_and_store_garmin_activities(
            db.session.get(User, user), pause=0
        )
        run = Run.query.one()  # the swim is skipped
        assert added == 1
        assert FakeGarmin.instances[0].tokenstore == TOKENS
        saved = pathlib.Path(run.fit_file_path)
        assert saved == pathlib.Path(app.config["FIT_STORAGE_DIR"]) / str(user) / "123.fit"
        assert saved.read_bytes() == b"FAKEFIT"


def test_legacy_password_is_swapped_for_tokens(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_password="garmin-secret")
    with app.app_context():
        garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user), pause=0)
        account = db.session.get(User, user)
        assert account.garmin_password is None
        assert account.garmin_tokens == TOKENS


def test_sync_skips_runs_already_stored(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        account = db.session.get(User, user)
        garmin_service.fetch_and_store_garmin_activities(account, pause=0)
        assert garmin_service.fetch_and_store_garmin_activities(account, pause=0) == 0
        assert Run.query.count() == 1


def test_archive_paths_never_decide_where_files_go(app, user, monkeypatch):
    monkeypatch.setattr(
        FakeGarmin, "download_activity", lambda self, a, dl_fmt=None: _fit_zip("../../evil.fit")
    )
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user), pause=0)
        saved = pathlib.Path(Run.query.one().fit_file_path)
        assert saved.parent == pathlib.Path(app.config["FIT_STORAGE_DIR"]) / str(user)
    assert not (pathlib.Path(app.config["FIT_STORAGE_DIR"]).parent.parent / "evil.fit").exists()


def test_linking_stores_tokens_never_the_password(app, auth_client, user, syncs):
    response = auth_client.post(
        "/garmin", data={"email": "g@example.com", "password": "garmin-secret"}
    )
    assert response.headers["Location"] == "/garmin"
    with app.app_context():
        account = db.session.get(User, user)
        assert account.garmin_tokens == TOKENS
        assert account.garmin_password is None
    assert syncs == [user]


def test_wrong_garmin_password_shows_an_error(auth_client, syncs):
    response = auth_client.post("/garmin", data={"email": "g@example.com", "password": "nope"})
    assert b"accept that sign-in" in response.data
    assert syncs == []


def test_two_step_verification(app, auth_client, user, syncs):
    FakeGarmin.needs_mfa = True
    page = auth_client.post("/garmin", data={"email": "g@example.com", "password": "garmin-secret"})
    assert b"verification code" in page.data
    auth_client.post("/garmin/verify", data={"code": "123456"})
    with app.app_context():
        assert db.session.get(User, user).garmin_tokens == TOKENS
    assert syncs == [user]


def test_wrong_verification_code_fails_and_ends_the_attempt(app, auth_client, user, syncs):
    FakeGarmin.needs_mfa = True
    auth_client.post("/garmin", data={"email": "g@example.com", "password": "garmin-secret"})
    auth_client.post("/garmin/verify", data={"code": "000000"})
    retry = auth_client.post("/garmin/verify", data={"code": "123456"}, follow_redirects=True)
    assert b"timed out" in retry.data
    assert syncs == []


def test_pending_sign_ins_belong_to_one_user():
    key = garmin_service.pending_logins.add(1, object())
    assert garmin_service.pending_logins.pop(key, 2) is None


def test_disconnect_forgets_garmin(app, auth_client, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    auth_client.post("/garmin/disconnect")
    with app.app_context():
        account = db.session.get(User, user)
        assert (account.garmin_username, account.garmin_tokens) == (None, None)


def test_background_sync_records_the_outcome(app, user, monkeypatch):
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(garmin_service.threading, "Thread", InlineThread)
    monkeypatch.setattr(garmin_service.time, "sleep", lambda seconds: None)
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    garmin_service.start_background_sync(app, user)
    with app.app_context():
        account = db.session.get(User, user)
        assert account.garmin_sync_state == "ok"
        assert account.garmin_sync_message == "1 new run imported."
        assert account.garmin_last_synced_at is not None
