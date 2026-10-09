"""What the dashboard shows: setup progress, training totals and recent weeks."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, UserSongHistory, utcnow


@dataclass
class Setup:
    """How far a runner is through getting their first results."""

    garmin_linked: bool
    spotify_linked: bool
    has_runs: bool
    has_music: bool  # song plays matched to runs
    has_results: bool  # at least one song scored

    @property
    def complete(self):
        return self.has_runs and self.has_music and self.has_results


def setup_state(user):
    """Work out ``user``'s :class:`Setup` from what is actually stored."""
    has_runs = db.session.query(Run.query.filter_by(user_id=user.id).exists()).scalar()
    has_music = db.session.query(
        UserSongHistory.query.filter(
            UserSongHistory.user_id == user.id, UserSongHistory.run_id.isnot(None)
        ).exists()
    ).scalar()
    has_results = db.session.query(
        RunSongAnalysis.query.filter(
            RunSongAnalysis.user_id == user.id, RunSongAnalysis.pace_delta.isnot(None)
        ).exists()
    ).scalar()
    return Setup(
        garmin_linked=bool(user.garmin_tokens or user.garmin_password),
        spotify_linked=bool(user.spotify_refresh_token),
        has_runs=bool(has_runs),
        has_music=bool(has_music),
        has_results=bool(has_results),
    )


@dataclass
class Totals:
    runs: int = 0
    metres: float = 0.0
    seconds: int = 0

    @property
    def pace(self):
        """Average pace in seconds per km, or ``None``."""
        return self.seconds / (self.metres / 1000) if self.metres else None


def totals(user_id, since=None):
    """Runs, distance and moving time for ``user_id``, optionally from ``since`` on."""
    query = db.session.query(
        func.count(Run.id),
        func.coalesce(func.sum(Run.distance), 0),
        func.coalesce(func.sum(Run.duration), 0),
    ).filter(Run.user_id == user_id)
    if since is not None:
        query = query.filter(Run.date_time >= since)
    runs, metres, seconds = query.one()
    return Totals(runs=runs, metres=float(metres), seconds=int(seconds))


def week_start(moment):
    """Midnight on the Monday of ``moment``'s week."""
    day = moment.date() - timedelta(days=moment.weekday())
    return datetime(day.year, day.month, day.day)


def weekly_distance(user_id, weeks=12, now=None):
    """Metres run in each of the last ``weeks`` weeks (Monday to Sunday), oldest first.

    Returns:
        ``(week_start, metres)`` pairs; weeks without runs are included with 0.
    """
    first = week_start(now or utcnow()) - timedelta(weeks=weeks - 1)
    by_week = {first + timedelta(weeks=i): 0.0 for i in range(weeks)}
    runs = db.session.query(Run.date_time, Run.distance).filter(
        Run.user_id == user_id, Run.date_time >= first
    )
    for started, metres in runs:
        key = week_start(started)
        if key in by_week:
            by_week[key] += metres or 0.0
    return sorted(by_week.items())
