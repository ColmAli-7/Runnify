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
import secrets
import threading
import time
import zipfile
from datetime import datetime

from fitparse import FitParseError
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from runnify.extensions import db
from runnify.models import Run, User, utcnow
from runnify.services.fit import parse_fit
from runnify.services.streams import save_stream

logger = logging.getLogger(__name__)

DOWNLOAD_FORMAT = Garmin.ActivityDownloadFormat.ORIGINAL  # zip containing the original .fit file
PAGE_SIZE = 20  # activities fetched per request
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


# --- syncing -----------------------------------------------------------------


def _client_for(user):
    """Return a signed-in Garmin client from the user's stored tokens (or legacy password)."""
    try:
        if user.garmin_tokens:
            client = Garmin()
            client.login(tokenstore=user.garmin_tokens)
        elif user.garmin_password:
            client = Garmin(user.garmin_username, user.garmin_password)
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


def _download_series(activity_id, client):
    """Download one activity and parse its FIT data into a :class:`Series` (``None`` on failure)."""
    try:
        data = _extract_fit(client.download_activity(activity_id, dl_fmt=DOWNLOAD_FORMAT))
        return parse_fit(data) if data else None
    except (*GARMIN_ERRORS, zipfile.BadZipFile, FitParseError) as error:
        logger.warning("Could not read FIT data for activity %s: %s", activity_id, error)
        return None


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


def fetch_and_store_garmin_activities(user, pause=1.0):
    """Download all new running activities for ``user`` and save them as ``Run`` rows.

    Pages through the user's Garmin activities, skips ones already stored and
    anything that isn't a run, stores each run's pace and heart-rate stream
    and commits one page at a time. Afterwards the (possibly refreshed) Garmin tokens are saved and
    any legacy stored password is erased.

    Args:
        user: The ``User`` to sync.
        pause: Seconds to wait between FIT downloads, to be gentle with Garmin.

    Returns:
        The number of runs added.

    Raises:
        GarminError: Signing in to Garmin failed.
    """
    client = _client_for(user)
    added = 0
    start = 0
    while activities := client.get_activities(start, PAGE_SIZE):
        for activity in activities:
            activity_id = str(activity["activityId"])
            if "running" not in activity.get("activityType", {}).get("typeKey", ""):
                continue
            stored = Run.query.filter_by(user_id=user.id, activity_id=activity_id).first()
            if stored:
                if stored.utc_offset is None:  # runs imported before local times were kept
                    stored.utc_offset = _utc_offset(
                        activity.get("startTimeLocal"), stored.date_time
                    )
                continue
            avg_speed = activity.get("averageSpeed") or 0.0
            started = datetime.strptime(activity["startTimeGMT"], GARMIN_TIME)
            run = Run(
                user_id=user.id,
                activity_id=activity_id,
                date_time=started,
                utc_offset=_utc_offset(activity.get("startTimeLocal"), started),
                distance=float(activity.get("distance") or 0),
                duration=int(activity.get("duration") or 0),
                avg_hr=activity.get("averageHR"),
                avg_pace=(1000 / avg_speed / 60) if avg_speed > 0 else None,  # min/km
            )
            db.session.add(run)
            db.session.flush()  # assigns run.id for the stream
            series = _download_series(activity_id, client)
            if series is not None:
                save_stream(run, series)
            added += 1
            time.sleep(pause)
        db.session.commit()
        start += PAGE_SIZE

    user.garmin_tokens = client.client.dumps()  # keep the refreshed session
    user.garmin_password = None  # legacy accounts: the password is no longer needed
    db.session.commit()
    return added


def start_background_sync(app, user_id):
    """Sync ``user_id``'s Garmin activities on a background thread, recording the outcome."""
    with app.app_context():
        user = db.session.get(User, user_id)
        user.garmin_sync_state, user.garmin_sync_message = "syncing", None
        db.session.commit()

    def run():
        with app.app_context():
            user = db.session.get(User, user_id)
            try:
                added = fetch_and_store_garmin_activities(user)
            except GarminError as error:
                user.garmin_sync_state, user.garmin_sync_message = "failed", str(error)
            except Exception:
                logger.exception("Garmin sync failed for user %s", user_id)
                db.session.rollback()
                user = db.session.get(User, user_id)
                user.garmin_sync_state = "failed"
                user.garmin_sync_message = "Something went wrong while syncing. Please try again."
            else:
                user.garmin_sync_state = "ok"
                user.garmin_sync_message = f"{added} new run{'s' if added != 1 else ''} imported."
                user.garmin_last_synced_at = utcnow()
            db.session.commit()

    threading.Thread(target=run, name=f"garmin-sync-{user_id}", daemon=True).start()
