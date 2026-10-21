"""Background jobs (a Garmin sync, a Spotify history import) and their progress.

Both run on a thread inside the web process, so a page never waits for them
(see ``docs/deployment.md``). A running job writes what it is doing and how
far it has got onto the user about once a second; pages read it from there,
and scripts poll it as JSON (:mod:`runnify.routes.jobs`).

A deploy or restart ends the thread without a word, which used to leave a
job "running" for ever and refuse every new one. Now a job that hasn't
reported for :data:`STALE_AFTER` counts as interrupted, and the runner can
start it again: a sync carries on where it stopped, and an upload adds only
what isn't stored yet.
"""

import time
from dataclasses import dataclass
from datetime import timedelta

from runnify.extensions import db
from runnify.models import User, utcnow

STALE_AFTER = timedelta(minutes=10)  # far longer than any step of a job waits
REPORT_EVERY = 1.0  # seconds between progress writes

# kind -> (column prefix on User, the state stored while it runs)
KINDS = {
    "garmin": ("garmin_sync", "syncing"),
    "history": ("history_import", "importing"),
}


@dataclass
class Job:
    """What one of the runner's jobs is doing, as the pages show it."""

    kind: str  # "garmin" or "history"
    state: str | None  # "running", "ok", "failed", "interrupted", or None if never run
    message: str | None  # what it is doing, or how it ended
    done: int | None = None
    total: int | None = None

    @property
    def running(self):
        return self.state == "running"

    @property
    def percent(self):
        """How far it has got, 0 to 100, or ``None`` while that isn't known."""
        if not self.running or not self.total or self.done is None:
            return None
        return max(0, min(100, round(100 * self.done / self.total)))

    def as_dict(self):
        return {
            "kind": self.kind,
            "state": self.state,
            "running": self.running,
            "message": self.message,
            "done": self.done,
            "total": self.total,
            "percent": self.percent,
        }


def job(user, kind):
    """The runner's ``kind`` of job ("garmin" or "history") as it stands now."""
    prefix, running = KINDS[kind]
    state = getattr(user, f"{prefix}_state")
    if state == running:
        updated = getattr(user, f"{prefix}_updated_at")
        state = "running" if updated and utcnow() - updated < STALE_AFTER else "interrupted"
    return Job(
        kind=kind,
        state=state,
        message=getattr(user, f"{prefix}_message"),
        done=getattr(user, f"{prefix}_done"),
        total=getattr(user, f"{prefix}_total"),
    )


def jobs_of(user):
    """``{"garmin": Job, "history": Job}`` for ``user``."""
    return {kind: job(user, kind) for kind in KINDS}


def _write(user, kind, state, message, done=None, total=None):
    prefix, _ = KINDS[kind]
    setattr(user, f"{prefix}_state", state)
    setattr(user, f"{prefix}_message", message)
    setattr(user, f"{prefix}_done", done)
    setattr(user, f"{prefix}_total", total)
    setattr(user, f"{prefix}_updated_at", utcnow())


def begin(user, kind, message=None):
    """Mark ``user``'s ``kind`` of job as running (the caller commits)."""
    _write(user, kind, KINDS[kind][1], message)


def end(user, kind, state, message):
    """Record how ``user``'s ``kind`` of job ended: ``"ok"`` or ``"failed"`` (the caller commits)."""
    _write(user, kind, state, message)


class Progress:
    """A running job's reports, written from the job's own thread.

    :meth:`report` commits the session, so callers report only where
    committing is safe: between whole runs, never halfway through one.

    Args:
        user_id: Whose job it is.
        kind: "garmin" or "history".
        every: Least seconds between writes; reports in between are dropped.
    """

    def __init__(self, user_id, kind, every=REPORT_EVERY):
        self.user_id, self.kind, self.every = user_id, kind, every
        self._last = None

    def report(self, message, done=None, total=None, force=False):
        """Record what the job is doing and how far it has got; ``True`` if written."""
        now = time.monotonic()
        if not force and self._last is not None and now - self._last < self.every:
            return False
        self._last = now
        _write(
            db.session.get(User, self.user_id), self.kind, KINDS[self.kind][1], message, done, total
        )
        db.session.commit()
        return True
