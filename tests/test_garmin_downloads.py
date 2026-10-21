"""Garmin syncs download a few runs at once and cope with a Garmin that stalls or pushes back."""

import io
import threading
import time
import zipfile
from datetime import datetime, timedelta
from itertools import pairwise

import pytest

from runnify.extensions import db
from runnify.models import Run, RunStream, User
from runnify.services import garmin as garmin_service
from runnify.services import jobs
from tests.fit_builder import build_fit

TOKENS = '{"di_token": "t", "di_refresh_token": "r", "di_client_id": "c"}'
NEWEST = datetime(2026, 10, 1, 7)
FIT = build_fit([(NEWEST + timedelta(seconds=i), 150, 3.0 * i, 3.0) for i in range(60)])


def _fit_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("run.fit", FIT)
    return buffer.getvalue()


class FakeTokens:
    def dumps(self):
        return TOKENS


class BusyGarmin:
    """A Garmin with ``runs`` runs three days apart (a swim after every third), newest first.

    Downloads take a moment, so they overlap. Activities in ``stall`` hang until
    ``release`` is set, ``refuse`` maps an activity to how many times Garmin
    answers "too many requests" before sending it, ``missing`` ones have no
    file, ``broken`` ones always fail, and ``sign_in`` can stall or refuse.
    """

    ActivityDownloadFormat = garmin_service.Garmin.ActivityDownloadFormat

    def __init__(self, *args, **kwargs):
        self.client = FakeTokens()

    def login(self, tokenstore=None):
        if BusyGarmin.sign_in == "stall":
            BusyGarmin.release.wait(5)
        return None, None

    @staticmethod
    def activities():
        found = []
        for n in range(BusyGarmin.runs):
            started = NEWEST - timedelta(days=3 * n)
            found.append(
                {
                    "activityId": 1000 + n,
                    "activityType": {"typeKey": "running"},
                    "startTimeGMT": started.strftime("%Y-%m-%d %H:%M:%S"),
                    "startTimeLocal": (started + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                    "duration": 1800.0,
                    "distance": 5000.0 + n,
                    "averageSpeed": 2.78,
                }
            )
            if n % 3 == 2:
                found.append(
                    {
                        **found[-1],
                        "activityId": 5000 + n,
                        "activityType": {"typeKey": "lap_swimming"},
                    }
                )
        return found

    def get_activities(self, start, limit):
        BusyGarmin.listed.append(start)
        return self.activities()[start : start + limit]

    def download_activity(self, activity_id, dl_fmt=None):
        activity_id = int(activity_id)
        with BusyGarmin.lock:
            BusyGarmin.active += 1
            BusyGarmin.most = max(BusyGarmin.most, BusyGarmin.active)
            BusyGarmin.started.append((activity_id, BusyGarmin.active))
        try:
            time.sleep(0.03)
            if activity_id in BusyGarmin.stall:
                BusyGarmin.release.wait(5)
            if BusyGarmin.refuse.get(activity_id, 0) > 0:
                BusyGarmin.refuse[activity_id] -= 1
                raise garmin_service.GarminConnectTooManyRequestsError("429")
            if activity_id in BusyGarmin.missing:
                raise garmin_service.GarminConnectNotFoundError("404")
            if activity_id in BusyGarmin.broken:
                raise garmin_service.GarminConnectConnectionError("500")
            if activity_id in BusyGarmin.rejected:
                raise garmin_service.GarminConnectAuthenticationError("401")
            return _fit_zip()
        finally:
            with BusyGarmin.lock:
                BusyGarmin.active -= 1


@pytest.fixture(autouse=True)
def busy_garmin(monkeypatch):
    BusyGarmin.runs, BusyGarmin.sign_in = 12, None
    BusyGarmin.stall, BusyGarmin.missing, BusyGarmin.broken, BusyGarmin.rejected = (
        set(),
        set(),
        set(),
        set(),
    )
    BusyGarmin.refuse, BusyGarmin.listed, BusyGarmin.started = {}, [], []
    BusyGarmin.lock, BusyGarmin.release = threading.Lock(), threading.Event()
    BusyGarmin.active = BusyGarmin.most = 0
    monkeypatch.setattr(garmin_service, "Garmin", BusyGarmin)
    monkeypatch.setattr(garmin_service, "CALL_TIMEOUT", 1.0)
    monkeypatch.setattr(garmin_service, "BEAT_EVERY", 0.05)
    monkeypatch.setattr(garmin_service, "BACKOFF", (0.05, 0.1, 0.15))
    yield BusyGarmin
    BusyGarmin.release.set()  # let any stalled download finish


@pytest.fixture
def linked(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.garmin_username, account.garmin_tokens = "g@example.com", TOKENS
        db.session.commit()
    return user


def _sync(app, user_id, progress=None):
    with app.app_context():
        return garmin_service.fetch_and_store_garmin_activities(
            db.session.get(User, user_id), progress=progress
        )


def _stored(app):
    with app.app_context():
        return [int(run.activity_id) for run in Run.query.order_by(Run.id)]


def test_three_runs_download_at_once_and_are_stored_newest_first(app, linked):
    assert _sync(app, linked) == garmin_service.Synced(added=12)
    assert BusyGarmin.most == 3
    assert _stored(app) == [1000 + n for n in range(12)]
    with app.app_context():
        assert RunStream.query.count() == 12
        assert all(run.laps for run in Run.query)


def test_a_stalled_download_is_left_for_the_next_sync(app, linked):
    BusyGarmin.stall = {1004}
    assert _sync(app, linked) == garmin_service.Synced(added=11, left=1)
    assert 1004 not in _stored(app)  # not kept without its samples
    BusyGarmin.release.set()
    BusyGarmin.stall = set()
    assert _sync(app, linked) == garmin_service.Synced(added=1)
    assert sorted(_stored(app)) == [1000 + n for n in range(12)]


def test_the_job_keeps_reporting_while_garmin_stalls(app, linked):
    BusyGarmin.stall = {1000}
    with app.app_context():
        progress = jobs.Progress(linked, "garmin", every=0)
        reports = []
        report = progress.report
        progress.report = lambda *args, **kwargs: (
            reports.append(time.monotonic()) or report(*args, **kwargs)
        )
    _sync(app, linked, progress)
    gaps = [later - earlier for earlier, later in pairwise(reports)]
    assert len(reports) > 20 and max(gaps) < 0.5  # never silent while it waited a second


def test_when_garmin_asks_to_slow_down_it_pauses_then_goes_one_at_a_time(app, linked, monkeypatch):
    pauses = []
    pause = garmin_service._Garmin._pause
    monkeypatch.setattr(
        garmin_service._Garmin, "_pause", lambda self, s: pauses.append(s) or pause(self, s)
    )
    BusyGarmin.refuse = {1003: 2}
    assert _sync(app, linked) == garmin_service.Synced(added=12)
    assert pauses == [0.05, 0.1]  # longer each time it was refused again
    starts = [activity_id for activity_id, _ in BusyGarmin.started]
    last_try = len(starts) - 1 - starts[::-1].index(1003)
    after = BusyGarmin.started[last_try + 1 :]
    assert after == [(1000 + n, 1) for n in range(4, 12)]  # then one at a time, in order
    assert _stored(app) == [1000 + n for n in range(12)]


def test_garmin_refusing_again_and_again_stops_the_sync_for_now(app, linked):
    BusyGarmin.refuse = {1000 + n: 99 for n in range(12)}
    synced = _sync(app, linked)
    assert synced == garmin_service.Synced(added=0, left=12, why="busy")
    assert garmin_service._summary(synced) == (
        "failed",
        "Garmin asked Runnify to slow down before any runs came in. "
        "Sync again in a while for your 12 new runs.",
    )
    BusyGarmin.refuse = {}
    assert _sync(app, linked).added == 12


@pytest.mark.parametrize(
    ("synced", "outcome"),
    [
        (garmin_service.Synced(3), ("ok", "3 new runs imported.")),
        (
            garmin_service.Synced(1, 4, "busy"),
            (
                "ok",
                "1 new run imported. Garmin asked Runnify to slow down, "
                "so 4 more will come in on your next sync.",
            ),
        ),
        (
            garmin_service.Synced(0, 2, "unreachable"),
            ("failed", "Garmin couldn't send your 2 new runs just now. Please sync again later."),
        ),
    ],
)
def test_what_a_sync_tells_the_runner(synced, outcome):
    assert garmin_service._summary(synced) == outcome


def test_an_activity_without_a_file_is_kept_without_samples(app, linked):
    BusyGarmin.missing = {1002}
    assert _sync(app, linked) == garmin_service.Synced(added=12)
    with app.app_context():
        run = Run.query.filter_by(activity_id="1002").one()
        assert db.session.get(RunStream, run.id) is None


def test_failed_downloads_wait_for_the_next_sync(app, linked):
    BusyGarmin.broken = {1001, 1007}
    synced = _sync(app, linked)
    assert synced == garmin_service.Synced(added=10, left=2)
    assert "2 couldn't be downloaded just now" in garmin_service._summary(synced)[1]


def test_a_garmin_failing_every_download_stops_the_sync_for_now(app, linked):
    BusyGarmin.broken = {1000 + n for n in range(12)}
    synced = _sync(app, linked)
    assert synced.added == 0 and synced.left == 12 and synced.why == "unreachable"


def test_a_stalled_sign_in_fails_the_sync_cleanly(app, linked):
    BusyGarmin.sign_in = "stall"
    with pytest.raises(garmin_service.GarminError, match="isn't responding"):
        _sync(app, linked)


def test_a_session_garmin_stops_accepting_fails_the_sync(app, linked):
    BusyGarmin.rejected = {1005}
    with pytest.raises(garmin_service.GarminError, match="didn't accept"):
        _sync(app, linked)
    assert len(_stored(app)) >= 5  # what came in before stays


def test_later_syncs_only_list_back_a_fortnight_before_the_last_full_one(app, linked, monkeypatch):
    monkeypatch.setattr(garmin_service, "PAGE_SIZE", 5)
    BusyGarmin.runs = 30  # three months of runs
    _sync(app, linked)
    assert BusyGarmin.listed[-1] >= 30  # the first sync lists everything
    with app.app_context():
        db.session.get(User, linked).garmin_last_synced_at = NEWEST + timedelta(days=1)
        db.session.commit()
    BusyGarmin.listed = []
    assert _sync(app, linked).added == 0
    assert BusyGarmin.listed == [0, 5]  # two pages reach back past the fortnight


def test_a_partial_sync_keeps_the_last_full_sync_time(app, linked, monkeypatch):
    class Inline:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(garmin_service, "threading", type("T", (), {"Thread": Inline}))
    BusyGarmin.broken = {1003}
    garmin_service.start_background_sync(app, linked)
    with app.app_context():
        account = db.session.get(User, linked)
        assert account.garmin_sync_state == "ok" and account.garmin_last_synced_at is None
        assert account.garmin_sync_message.startswith("11 new runs imported. 1 couldn't")
    BusyGarmin.broken = set()
    garmin_service.start_background_sync(app, linked)
    with app.app_context():
        account = db.session.get(User, linked)
        assert account.garmin_sync_message == "1 new run imported."
        assert account.garmin_last_synced_at is not None
