"""Garmin Connect: account linking and activity sync.

Runnify never keeps a Garmin password. Linking signs in once (including
Garmin's own two-step verification when the account uses it) and stores the
resulting Garmin session tokens, encrypted at rest. Syncs resume from those
tokens; the library refreshes them as needed and the fresh copy is saved after
each sync. Accounts linked before this existed had their password stored; the
next sync swaps it for tokens and erases the password.

Sign-ins awaiting a two-step code are held in this process's memory for five
minutes, so the code must reach the same server process (one instance, or
sticky sessions).
"""

import io
import logging
import re
import secrets
import threading
import time
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from runnify.extensions import db
from runnify.models import Run, User, utcnow
from runnify.services import jobs
from runnify.services.analysis import rescore_run
from runnify.services.fit import parse_fit
from runnify.services.laps import UsualPaces, pace_of, refresh_laps, retype_runs
from runnify.services.streams import FORMAT_VERSION, save_stream, stored_format

logger = logging.getLogger(__name__)

DOWNLOAD_FORMAT = Garmin.ActivityDownloadFormat.ORIGINAL  # zip containing the original .fit file
PAGE_SIZE = 100  # activities listed per request
MAX_FIT_BYTES = 50 * 1024 * 1024  # a FIT file is a few MB at most; refuse anything absurd
MFA_TTL_SECONDS = 300


class GarminError(Exception):
    """A Garmin problem, with a message that is safe to show the user."""


def _friendly(error):
    """Translate a garminconnect exception into a :class:`GarminError`."""
    if isinstance(error, GarminConnectAuthenticationError):
        return GarminError("Garmin didn't accept that sign-in. Check your email, password or code.")
    if isinstance(error, GarminConnectTooManyRequestsError):
        return GarminError(
            "Garmin is limiting sign-ins right now. Please try again in a few minutes."
        )
    return GarminError("Garmin couldn't be reached. Please try again later.")


GARMIN_ERRORS = (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


# --- linking -----------------------------------------------------------------


class _PendingLogins:
    """Garmin clients waiting for a two-step verification code, keyed by a random id."""

    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def add(self, user_id, client):
        key = secrets.token_urlsafe(24)
        with self._lock:
            self._purge()
            self._items[key] = (user_id, client, time.monotonic() + MFA_TTL_SECONDS)
        return key

    def pop(self, key, user_id):
        with self._lock:
            self._purge()
            owner, client, _ = self._items.pop(key, (None, None, None))
        return client if owner == user_id else None

    def _purge(self):
        now = time.monotonic()
        for key in [k for k, (_, _, expires) in self._items.items() if expires < now]:
            del self._items[key]


pending_logins = _PendingLogins()


def begin_link(user, email, password):
    """Sign in to Garmin with the user's credentials.

    Returns:
        ``None`` when linking is complete, or a key identifying the pending
        sign-in when Garmin asks for a two-step verification code.

    Raises:
        GarminError: Garmin refused the sign-in or couldn't be reached.
    """
    client = Garmin(email, password, return_on_mfa=True)
    try:
        status, _ = client.login()
    except GARMIN_ERRORS as error:
        raise _friendly(error) from error
    if status == "needs_mfa":
        return pending_logins.add(user.id, client)
    _store_link(user, email, client)
    return None


def finish_link(user, pending_key, code):
    """Complete a pending sign-in with the two-step verification ``code``.

    Raises:
        GarminError: The pending sign-in expired, or Garmin rejected the code.
    """
    client = pending_logins.pop(pending_key, user.id)
    if client is None:
        raise GarminError("That Garmin sign-in timed out. Please start again.")
    try:
        client.resume_login(None, code)
    except GARMIN_ERRORS as error:
        raise _friendly(error) from error
    _store_link(user, client.username, client)


def _store_link(user, email, client):
    user.garmin_username = email
    user.garmin_tokens = client.client.dumps()
    user.garmin_password = None


def unlink(user):
    """Forget the user's Garmin account (tokens, legacy password and sync status)."""
    user.garmin_username = user.garmin_tokens = user.garmin_password = None
    user.garmin_sync_state = user.garmin_sync_message = None
    user.garmin_last_synced_at = None  # the next account linked starts afresh


# --- syncing -----------------------------------------------------------------

DOWNLOAD_WORKERS = 3  # FIT files downloading at once
CALL_TIMEOUT = 90  # seconds one call to Garmin may take (its own retries included) before it stalls
BEAT_EVERY = 5  # seconds between heartbeats while waiting on Garmin
BACKOFF = (60, 120, 240)  # seconds to pause each time Garmin asks Runnify to slow down
MAX_FAILURES = 5  # downloads failing in a row before a sync stops for now
RETRY_LATER = object()  # a download that stalled or failed, for the next sync


class _Stalled(Exception):
    """A call to Garmin took longer than :data:`CALL_TIMEOUT`."""


class _Stop(Exception):
    """The sync stops for now; ``left`` runs wait for the next one."""

    def __init__(self, left, why):
        super().__init__(why)
        self.left, self.why = left, why


@dataclass
class Synced:
    """What a sync brought in."""

    added: int
    left: int = 0  # runs it couldn't download this time, for the next sync
    why: str | None = None  # "busy" when Garmin asked Runnify to slow down


def _client_from(tokens, username, password):
    """A signed-in Garmin client from stored tokens (or a legacy stored password)."""
    try:
        if tokens:
            client = Garmin()
            client.login(tokenstore=tokens)
        elif password:
            client = Garmin(username, password)
            client.login()
        else:
            raise GarminError("Garmin isn't connected.")
    except GARMIN_ERRORS as error:
        raise _friendly(error) from error
    return client


def _extract_fit(zip_bytes):
    """Return the bytes of the first ``.fit`` file in a Garmin download, or ``None``.

    Only the FIT entry is read, in memory and with a size cap; nothing in the
    archive is ever written to disk.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for entry in archive.infolist():
            if entry.filename.lower().endswith(".fit") and entry.file_size <= MAX_FIT_BYTES:
                return archive.read(entry)
    return None


def _fetch(client, activity_id):
    """Download one activity and read its samples (``None`` if it has none Runnify can read).

    Runs on a worker thread; Garmin's own errors are the caller's to handle.
    """
    download = client.download_activity(activity_id, dl_fmt=DOWNLOAD_FORMAT)
    try:
        data = _extract_fit(download)
        return parse_fit(data) if data else None
    except Exception as error:  # the file is Garmin's to vouch for: keep the run without samples
        logger.warning("Could not read FIT data for activity %s: %s", activity_id, error)
        return None


_STATUS = re.compile(r"(?:error \(|Error |HTTP )([1-5]\d\d)\b")


def _status(error):
    """The HTTP status behind a garminconnect error, when it says (``None`` if not)."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status, int):
        return status
    match = _STATUS.search(str(error))
    return int(match.group(1)) if match else None


def _await(future, seconds, beat):
    """``future``'s result, calling ``beat`` every few seconds; :class:`_Stalled` after ``seconds``."""
    deadline = time.monotonic() + seconds
    while True:
        done, _ = wait([future], timeout=max(0.0, min(BEAT_EVERY, deadline - time.monotonic())))
        if done:
            return future.result()
        if time.monotonic() >= deadline:
            raise _Stalled
        beat()


class _Garmin:
    """Calls to Garmin on a few worker threads, so a stall never holds the sync for long.

    Garmin can stall for minutes. Each call here may take :data:`CALL_TIMEOUT`
    at most, and the job keeps reporting while it waits (``beat``), so it never
    looks interrupted. When Garmin asks Runnify to slow down (HTTP 429), the
    downloads pause for longer each time and carry on one at a time.
    """

    def __init__(self, workers=DOWNLOAD_WORKERS, beat=lambda: None):
        self.workers, self.beat = workers, beat
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="garmin")

    def call(self, function, *args):
        """``function(*args)`` on a worker thread, Garmin's problems as a :class:`GarminError`."""
        try:
            return _await(self.pool.submit(function, *args), CALL_TIMEOUT, self.beat)
        except _Stalled as error:
            raise GarminError("Garmin isn't responding. Please try again later.") from error
        except GARMIN_ERRORS as error:
            raise _friendly(error) from error

    def _pause(self, seconds):
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            time.sleep(min(BEAT_EVERY, left))
            self.beat()

    def downloads(self, client, activity_ids):
        """Yield ``(activity id, series)`` in order, downloading a few ahead.

        ``series`` is ``None`` for an activity without FIT data Runnify can read
        (a run entered by hand, say), or :data:`RETRY_LATER` for one that
        stalled or failed this time.

        Raises:
            _Stop: Garmin kept asking Runnify to slow down, or kept failing.
            GarminError: Garmin stopped accepting the session.
        """
        queue, ahead = deque(activity_ids), deque()
        limit, backoff, failures = self.workers, iter(BACKOFF), 0
        while queue or ahead:
            while queue and len(ahead) < limit:
                activity_id = queue.popleft()
                ahead.append((activity_id, self.pool.submit(_fetch, client, activity_id)))
            activity_id, future = ahead.popleft()
            try:
                series = _await(future, CALL_TIMEOUT, self.beat)
            except _Stalled:
                logger.warning("Garmin stalled sending activity %s", activity_id)
                series = RETRY_LATER
            except GarminConnectTooManyRequestsError:
                # whatever else is on its way was likely refused too: all of it again, later
                for _, waiting in ahead:
                    waiting.cancel()
                queue.extendleft(reversed([activity_id, *(queued for queued, _ in ahead)]))
                ahead.clear()
                pause = next(backoff, None)
                if pause is None:
                    raise _Stop(len(queue), "busy") from None
                logger.warning("Garmin asked to slow down; pausing for %s s", pause)
                limit = 1
                self._pause(pause)
                continue
            except GarminConnectAuthenticationError as error:
                raise _friendly(error) from error
            except GarminConnectNotFoundError:  # nothing to download
                series = None
            except GarminConnectConnectionError as error:
                if 400 <= (_status(error) or 0) < 500:  # refused for good: asking again won't help
                    logger.warning("Garmin refused activity %s for good: %s", activity_id, error)
                    series = None
                else:  # Garmin's servers or the network: worth another try next time
                    logger.warning("Could not download activity %s: %s", activity_id, error)
                    series = RETRY_LATER
            if series is RETRY_LATER:
                failures += 1
                if failures >= MAX_FAILURES:
                    raise _Stop(len(queue) + len(ahead) + 1, "unreachable")
            else:
                failures, backoff = 0, iter(BACKOFF)
            yield activity_id, series

    def close(self):
        """Stop starting downloads; any still running finish on their own."""
        self.pool.shutdown(wait=False, cancel_futures=True)


GARMIN_TIME = "%Y-%m-%d %H:%M:%S"


def _utc_offset(local_text, started_utc):
    """Minutes the runner's clock was ahead of UTC, from Garmin's local start time (or ``None``)."""
    try:
        local = datetime.strptime(local_text or "", GARMIN_TIME)
    except ValueError:
        return None
    minutes = (
        round((local - started_utc).total_seconds() / 60 / 15) * 15
    )  # zones run in quarter hours
    return minutes if abs(minutes) <= 14 * 60 else None


def _is_run(activity):
    return "running" in (activity.get("activityType") or {}).get("typeKey", "")


def _list_runs(garmin, client, say):
    """Every running activity Garmin lists, newest first.

    Every sync lists them all, 100 to a request: it costs little next to the
    downloads, and nothing waiting (a run uploaded late, one left for the next
    sync, a newly linked account's) can be missed.
    """
    runs, seen, start = [], set(), 0
    while page := garmin.call(client.get_activities, start, PAGE_SIZE):
        for activity in page:
            activity_id = str(activity["activityId"])
            if _is_run(activity) and activity_id not in seen:  # a new upload can shift a page
                seen.add(activity_id)
                runs.append(activity)
        start += len(page)
        say(f"Looking for new runs: {start:,} activities checked")
    return runs


def _run_from(user_id, activity):
    """A new :class:`Run` from Garmin's description of ``activity``."""
    avg_speed = activity.get("averageSpeed") or 0.0
    started = datetime.strptime(activity["startTimeGMT"], GARMIN_TIME)
    return Run(
        user_id=user_id,
        activity_id=str(activity["activityId"]),
        date_time=started,
        utc_offset=_utc_offset(activity.get("startTimeLocal"), started),
        distance=float(activity.get("distance") or 0),
        duration=int(activity.get("duration") or 0),
        avg_hr=activity.get("averageHR"),
        avg_pace=(1000 / avg_speed / 60) if avg_speed > 0 else None,  # min/km
    )


def _store(user_id, activity, series, usual):
    """Store one downloaded run with its samples and laps; ``False`` if it was already there."""
    activity_id = str(activity["activityId"])
    if Run.query.filter_by(user_id=user_id, activity_id=activity_id).first():
        return False  # another sync got there first
    run = _run_from(user_id, activity)
    db.session.add(run)
    db.session.flush()  # assigns run.id for the stream
    if series is not None:
        save_stream(run, series)
        refresh_laps(run, series, usual)
    db.session.commit()
    return True


def _reporter(progress):
    """``(say, beat)``: report what the sync is doing, and repeat it while waiting on Garmin."""
    state = {"message": "Signing in to Garmin", "done": None, "total": None}

    def say(message, done=None, total=None):
        state.update(message=message, done=done, total=total)
        if progress:
            progress.report(message, done, total)

    def beat():
        if progress:
            progress.report(**state)

    return say, beat


def fetch_and_store_garmin_activities(user, progress=None, workers=DOWNLOAD_WORKERS):
    """Download the runner's new runs from Garmin and store each with its samples and laps.

    Lists all of the runner's activities, skips anything that isn't a run or is
    already stored, then downloads the rest a few at a time (see
    :class:`_Garmin`), storing and committing each run as it arrives, newest
    first. A download that stalls, or fails on Garmin's side, is left for the
    next sync rather than stored without its samples; one Garmin has no file
    for, or refuses outright (a 4xx), is kept without them. Each run's laps are
    judged against the runner's usual pace over every run, new ones included.
    Afterwards every run's type is worked out again, the (possibly refreshed)
    Garmin tokens are saved and any legacy stored password is erased.

    Args:
        user: The ``User`` to sync.
        progress: A :class:`runnify.services.jobs.Progress` to report to.
        workers: FIT files to download at once.

    Returns:
        A :class:`Synced`.

    Raises:
        GarminError: Signing in failed, Garmin stopped accepting the session,
            or it isn't responding.
    """
    say, beat = _reporter(progress)
    user_id = user.id
    garmin = _Garmin(workers, beat)
    try:
        client = garmin.call(
            _client_from, user.garmin_tokens, user.garmin_username, user.garmin_password
        )
        stored = {
            activity_id: (run_id, started, offset, pace_of(duration, distance))
            for activity_id, run_id, started, offset, duration, distance in db.session.query(
                Run.activity_id, Run.id, Run.date_time, Run.utc_offset, Run.duration, Run.distance
            ).filter(Run.user_id == user_id)
        }
        say("Looking for new runs")
        new = {}
        for activity in _list_runs(garmin, client, say):
            activity_id = str(activity["activityId"])
            if activity_id not in stored:
                new[activity_id] = activity
                continue
            run_id, started, offset, _ = stored[activity_id]
            if offset is None:
                db.session.get(Run, run_id).utc_offset = _utc_offset(
                    activity.get("startTimeLocal"), started
                )
        db.session.commit()

        paces = {activity_id: pace for activity_id, (*_, pace) in stored.items()}
        for activity_id, activity in new.items():
            paces[activity_id] = pace_of(
                int(activity.get("duration") or 0), float(activity.get("distance") or 0)
            )
        usual = UsualPaces({key: pace for key, pace in paces.items() if pace is not None})
        added = retry = left = 0
        why = None
        say(f"Bringing in your runs: 0 of {len(new):,}", 0, len(new))
        try:
            for done, (activity_id, series) in enumerate(garmin.downloads(client, list(new)), 1):
                if series is RETRY_LATER:
                    retry += 1
                elif _store(user_id, new[activity_id], series, usual.excluding(activity_id)):
                    added += 1
                say(f"Bringing in your runs: {done:,} of {len(new):,}", done, len(new))
        except _Stop as stop:
            left, why = stop.left, stop.why

        retype_runs(user_id)
        user = db.session.get(User, user_id)
        user.garmin_tokens = client.client.dumps()  # keep the refreshed session
        user.garmin_password = None  # legacy accounts: the password is no longer needed
        db.session.commit()
        return Synced(added, retry + left, why)
    finally:
        garmin.close()


def refetch_runs(user, workers=DOWNLOAD_WORKERS, progress=None):
    """Download again the FIT files of ``user``'s runs stored before laps and cadence were kept.

    Each such run gets a fresh stream, its laps worked out again (unless the
    runner set them by hand) and its songs measured again, a run at a time;
    the refreshed Garmin session is saved afterwards. Runs whose stream is
    already current are left alone, so it can be run again safely.

    Returns:
        How many runs were refreshed.

    Raises:
        GarminError: Signing in to Garmin failed, or it isn't responding.
    """
    say, beat = _reporter(progress)
    user_id = user.id
    stale = {
        run.activity_id: run.id
        for run in Run.query.filter_by(user_id=user_id).order_by(Run.date_time.desc())
        if stored_format(run) < FORMAT_VERSION
    }
    garmin = _Garmin(workers, beat)
    refreshed = 0
    try:
        client = garmin.call(
            _client_from, user.garmin_tokens, user.garmin_username, user.garmin_password
        )
        usual = UsualPaces.for_runner(user_id)
        try:
            for done, (activity_id, series) in enumerate(garmin.downloads(client, list(stale)), 1):
                if series is not None and series is not RETRY_LATER:
                    run = db.session.get(Run, stale[activity_id])
                    save_stream(run, series)
                    rescore_run(run, series, usual=usual.excluding(run.id))
                    db.session.commit()
                    refreshed += 1
                say(f"Downloading your runs again: {done:,} of {len(stale):,}", done, len(stale))
        except _Stop:
            pass  # the rest wait for the next time
        retype_runs(user_id)
        user = db.session.get(User, user_id)
        user.garmin_tokens = client.client.dumps()  # keep the refreshed session
        user.garmin_password = None
        db.session.commit()
        return refreshed
    finally:
        garmin.close()


def _summary(synced):
    """How a finished sync went (``"ok"`` or ``"failed"``) and what it tells the runner."""
    added, left = synced.added, synced.left
    imported = f"{added} new run{'s' if added != 1 else ''} imported."
    if not left:
        return "ok", imported
    if synced.why == "busy":
        if not added:
            return "failed", (
                "Garmin asked Runnify to slow down before any runs came in. "
                f"Sync again in a while for your {left:,} new run{'s' if left != 1 else ''}."
            )
        return "ok", (
            f"{imported} Garmin asked Runnify to slow down, "
            f"so {left:,} more will come in on your next sync."
        )
    if synced.why == "unreachable" and not added:
        return "failed", (
            f"Garmin couldn't send your {left:,} new run{'s' if left != 1 else ''} just now. "
            "Please sync again later."
        )
    waiting = "1 couldn't" if left == 1 else f"{left:,} couldn't"
    return "ok", (
        f"{imported if added else 'No new runs imported.'} {waiting} be downloaded just now "
        "and will be tried again on your next sync."
    )


def start_background_sync(app, user_id):
    """Sync ``user_id``'s Garmin activities on a background thread, recording the outcome."""
    with app.app_context():
        jobs.begin(db.session.get(User, user_id), "garmin", "Starting the sync")
        db.session.commit()

    def run():
        with app.app_context():
            user = db.session.get(User, user_id)
            try:
                synced = fetch_and_store_garmin_activities(
                    user, progress=jobs.Progress(user_id, "garmin")
                )
            except GarminError as error:
                db.session.rollback()
                jobs.end(db.session.get(User, user_id), "garmin", "failed", str(error))
            except Exception:
                logger.exception("Garmin sync failed for user %s", user_id)
                db.session.rollback()
                jobs.end(
                    db.session.get(User, user_id),
                    "garmin",
                    "failed",
                    "Something went wrong while syncing. Please try again.",
                )
            else:
                user = db.session.get(User, user_id)
                state, message = _summary(synced)
                jobs.end(user, "garmin", state, message)
                if state == "ok":
                    user.garmin_last_synced_at = utcnow()
            db.session.commit()

    threading.Thread(target=run, name=f"garmin-sync-{user_id}", daemon=True).start()
