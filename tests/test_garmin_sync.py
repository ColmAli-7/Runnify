"""Garmin linking and sync, with a fake Garmin client."""

import io
import json
import pathlib
import zipfile
import zlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from runnify.extensions import db
from runnify.models import Run, RunStream, User
from runnify.services import garmin as garmin_service
from tests.fit_builder import build_fit

TOKENS = json.dumps({"di_token": "t", "di_refresh_token": "r", "di_client_id": "c"})


FIT = build_fit(
    [(datetime(2026, 10, 1, 7) + timedelta(seconds=i), 150, 3.0 * i, 3.0) for i in range(60)]
)


def _fit_zip(name="123_ACTIVITY.fit", data=FIT):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, data)
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
        common = {
            "startTimeGMT": "2026-10-01 07:00:00",
            "startTimeLocal": "2026-10-01 08:00:00",  # Irish summer time
            "duration": 1800.0,
            "distance": 5000.0,
        }
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


def test_sync_from_tokens_saves_runs_and_their_streams(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        synced = garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user))
        run = Run.query.one()  # the swim is skipped
        assert synced == garmin_service.Synced(added=1)
        assert FakeGarmin.instances[0].tokenstore == TOKENS
        assert db.session.get(RunStream, run.id).sample_count == 60
        assert run.fit_file_path is None  # no FIT file is kept
        assert run.utc_offset == 60 and run.local_start.hour == 8
        assert [lap.kind for lap in run.laps] == ["steady"] and run.laps_source == "detected"
        assert run.run_type == "easy"


def test_legacy_password_is_swapped_for_tokens(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_password="garmin-secret")
    with app.app_context():
        garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user))
        account = db.session.get(User, user)
        assert account.garmin_password is None
        assert account.garmin_tokens == TOKENS


def test_sync_skips_runs_already_stored(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        account = db.session.get(User, user)
        garmin_service.fetch_and_store_garmin_activities(account)
        assert garmin_service.fetch_and_store_garmin_activities(account).added == 0
        assert Run.query.count() == 1


def test_downloads_are_never_written_to_disk(app, user, monkeypatch, tmp_path):
    monkeypatch.setattr(
        FakeGarmin, "download_activity", lambda self, a, dl_fmt=None: _fit_zip("../../evil.fit")
    )
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user))
        assert db.session.get(RunStream, Run.query.one().id) is not None
    assert not list(pathlib.Path(tmp_path).rglob("*.fit"))


def test_unreadable_fit_data_still_saves_the_run(app, user, monkeypatch):
    monkeypatch.setattr(
        FakeGarmin, "download_activity", lambda self, a, dl_fmt=None: _fit_zip(data=b"not fit")
    )
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user))
        assert db.session.get(RunStream, Run.query.one().id) is None


def test_linking_stores_tokens_never_the_password(app, auth_client, user, syncs):
    response = auth_client.post(
        "/connections/garmin", data={"email": "g@example.com", "password": "garmin-secret"}
    )
    assert response.headers["Location"] == "/connections"
    with app.app_context():
        account = db.session.get(User, user)
        assert account.garmin_tokens == TOKENS
        assert account.garmin_password is None
    assert syncs == [user]


def test_wrong_garmin_password_shows_an_error(auth_client, syncs):
    response = auth_client.post(
        "/connections/garmin", data={"email": "g@example.com", "password": "nope"}
    )
    assert b"accept that sign-in" in response.data
    assert syncs == []


def test_two_step_verification(app, auth_client, user, syncs):
    FakeGarmin.needs_mfa = True
    page = auth_client.post(
        "/connections/garmin", data={"email": "g@example.com", "password": "garmin-secret"}
    )
    assert b"verification code" in page.data
    auth_client.post("/connections/garmin/verify", data={"code": "123456"})
    with app.app_context():
        assert db.session.get(User, user).garmin_tokens == TOKENS
    assert syncs == [user]


def test_wrong_verification_code_fails_and_ends_the_attempt(app, auth_client, user, syncs):
    FakeGarmin.needs_mfa = True
    auth_client.post(
        "/connections/garmin", data={"email": "g@example.com", "password": "garmin-secret"}
    )
    auth_client.post("/connections/garmin/verify", data={"code": "000000"})
    retry = auth_client.post(
        "/connections/garmin/verify", data={"code": "123456"}, follow_redirects=True
    )
    assert b"timed out" in retry.data
    assert syncs == []


def test_pending_sign_ins_belong_to_one_user():
    key = garmin_service.pending_logins.add(1, object())
    assert garmin_service.pending_logins.pop(key, 2) is None


def test_disconnect_forgets_garmin(app, auth_client, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    auth_client.post("/connections/garmin/disconnect")
    with app.app_context():
        account = db.session.get(User, user)
        assert (account.garmin_username, account.garmin_tokens) == (None, None)


def test_background_sync_records_the_outcome(app, user, monkeypatch):
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    # only the sync's own thread runs inline: the download pool keeps real threads
    monkeypatch.setattr(garmin_service, "threading", SimpleNamespace(Thread=InlineThread))
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    garmin_service.start_background_sync(app, user)
    with app.app_context():
        account = db.session.get(User, user)
        assert account.garmin_sync_state == "ok"
        assert account.garmin_sync_message == "1 new run imported."
        assert account.garmin_last_synced_at is not None


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        ("2026-10-01 08:00:00", 60),
        ("2026-10-01 01:30:01", -330),  # a stray second rounds to the zone
        ("2026-10-02 07:00:00", None),  # a day out is not a time zone
        (None, None),
        ("not a time", None),
    ],
)
def test_utc_offset_from_garmin_local_time(local, expected):
    assert garmin_service._utc_offset(local, datetime(2026, 10, 1, 7, 0)) == expected


def test_sync_fills_in_local_time_for_runs_stored_without_it(app, user):
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    with app.app_context():
        db.session.add(Run(user_id=user, activity_id="123", date_time=datetime(2026, 10, 1, 7, 0)))
        db.session.commit()
        garmin_service.fetch_and_store_garmin_activities(db.session.get(User, user))
        assert Run.query.one().utc_offset == 60


# half an hour at 5:33/km, recorded following a workout: warm-up, run, cool-down
WORKOUT_FIT = build_fit(
    [(datetime(2026, 10, 1, 7) + timedelta(seconds=i), 150, 3.0 * i, 3.0) for i in range(1800)],
    laps=[
        (datetime(2026, 10, 1, 7, 0), 600, 2, 1, 0),
        (datetime(2026, 10, 1, 7, 10), 600, 0, 1, 1),
        (datetime(2026, 10, 1, 7, 20), 600, 3, 7, 2),
    ],
)


def _old_run(app, user):
    """A run stored before laps were kept: its stream is format 1."""
    with app.app_context():
        run = Run(
            user_id=user, activity_id="123", date_time=datetime(2026, 10, 1, 7), duration=1800
        )
        db.session.add(run)
        db.session.flush()
        old = {"v": 1, "t": [0, 1], "p": [300.0, 300.0], "h": [150, 150]}
        db.session.add(
            RunStream(
                run_id=run.id,
                started_at=run.date_time,
                sample_count=2,
                samples=zlib.compress(json.dumps(old).encode()),
            )
        )
        db.session.commit()


def test_refetching_old_runs_keeps_the_watchs_laps(app, user, monkeypatch):
    monkeypatch.setattr(
        FakeGarmin, "download_activity", lambda self, a, dl_fmt=None: _fit_zip(data=WORKOUT_FIT)
    )
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    _old_run(app, user)
    with app.app_context():
        assert garmin_service.refetch_runs(db.session.get(User, user)) == 1
        run = Run.query.one()
        assert run.laps_source == "watch"
        assert [lap.kind for lap in run.laps] == ["warmup", "steady", "cooldown"]
        assert db.session.get(RunStream, run.id).sample_count == 1800
        # already current: nothing to fetch the second time
        assert garmin_service.refetch_runs(db.session.get(User, user)) == 0


def test_the_refetch_command_skips_runners_without_garmin(app, user, monkeypatch):
    monkeypatch.setattr(
        FakeGarmin, "download_activity", lambda self, a, dl_fmt=None: _fit_zip(data=WORKOUT_FIT)
    )
    _set(app, user, garmin_username="g@example.com", garmin_tokens=TOKENS)
    _old_run(app, user)
    with app.app_context():
        unlinked = User(name="Unlinked", email="u@example.com", password_hash="unused")
        unlinked.garmin_username = "u@example.com"  # linked once, tokens since removed
        db.session.add(unlinked)
        db.session.commit()
        unlinked_id = unlinked.id
    result = app.test_cli_runner().invoke(args=["laps", "refetch"])
    assert f"Skipped user {unlinked_id}: Garmin isn't connected." in result.output
    assert "Refreshed 1 run from Garmin." in result.output
