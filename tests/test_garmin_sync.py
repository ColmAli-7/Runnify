"""Tests for the Garmin activity sync (with a fake Garmin client)."""

import io
import pathlib
import zipfile

from cryptography.fernet import Fernet

from runnify.extensions import db
from runnify.models import Run, User
from runnify.services import garmin as garmin_service


def _fit_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("123_ACTIVITY.fit", b"FAKEFIT")
    return buffer.getvalue()


class FakeGarmin:
    """Stands in for ``garminconnect.Garmin``: one run and one swim."""

    ActivityDownloadFormat = garmin_service.Garmin.ActivityDownloadFormat

    def __init__(self, email, password):
        self.password = password

    def login(self):
        assert self.password == "garmin-secret"

    def get_activities(self, start, limit):
        if start:
            return []
        common = {"startTimeGMT": "2026-10-01 07:00:00", "duration": 1800.0, "distance": 5000.0}
        return [
            {"activityId": 123, "activityType": {"typeKey": "running"}, "averageHR": 150, "averageSpeed": 2.78, **common},
            {"activityId": 456, "activityType": {"typeKey": "lap_swimming"}, **common},
        ]

    def download_activity(self, activity_id, dl_fmt=None):
        return _fit_zip()


def test_sync_saves_runs_and_their_fit_files(app, monkeypatch):
    monkeypatch.setattr(garmin_service, "Garmin", FakeGarmin)
    fernet = Fernet(app.config["FERNET_KEY"].encode())
    with app.app_context():
        user = User(
            name="T",
            email="t@example.com",
            password_hash="x",
            garmin_username="g@example.com",
            garmin_password=fernet.encrypt(b"garmin-secret").decode(),
        )
        db.session.add(user)
        db.session.commit()

        garmin_service.fetch_and_store_garmin_activities(user, fernet)

        run = Run.query.one()  # the swim is skipped
        assert run.activity_id == "123"
        saved = pathlib.Path(run.fit_file_path)
        assert saved.suffix == ".fit"
        assert saved.read_bytes() == b"FAKEFIT"


def test_sync_skips_activities_already_stored(app, monkeypatch):
    monkeypatch.setattr(garmin_service, "Garmin", FakeGarmin)
    fernet = Fernet(app.config["FERNET_KEY"].encode())
    with app.app_context():
        user = User(
            name="T",
            email="t@example.com",
            password_hash="x",
            garmin_username="g@example.com",
            garmin_password=fernet.encrypt(b"garmin-secret").decode(),
        )
        db.session.add(user)
        db.session.commit()

        garmin_service.fetch_and_store_garmin_activities(user, fernet)
        garmin_service.fetch_and_store_garmin_activities(user, fernet)

        assert Run.query.count() == 1
