"""Account data rights: export everything we hold about a user, or delete it all.

The export never includes secrets (password hash, tokens, two-step secrets).
Deletion removes every personal row and the user's stored FIT files; the
shared song catalogue (track names and artists) is not personal data and is
kept.
"""

import shutil
from pathlib import Path

from flask import current_app
from sqlalchemy import delete, or_

from runnify.extensions import db
from runnify.models import (
    FriendRequest,
    RecoveryCode,
    Run,
    RunSongAnalysis,
    SecurityEvent,
    Song,
    UserSongHistory,
    friends,
    utcnow,
)
from runnify.security.audit import DESCRIPTIONS


def _iso(value):
    return value.isoformat() + "Z" if value else None


def export_data(user):
    """Return a JSON-ready dict of everything Runnify stores about ``user``."""
    runs = Run.query.filter_by(user_id=user.id).order_by(Run.date_time).all()
    activity_ids = {run.id: run.activity_id for run in runs}
    plays = (
        db.session.query(UserSongHistory, Song)
        .join(Song, Song.id == UserSongHistory.song_id)
        .filter(UserSongHistory.user_id == user.id)
        .order_by(UserSongHistory.played_at)
        .all()
    )
    scores = (
        db.session.query(RunSongAnalysis, UserSongHistory)
        .join(UserSongHistory, UserSongHistory.id == RunSongAnalysis.user_song_id)
        .filter(RunSongAnalysis.user_id == user.id)
        .all()
    )
    events = SecurityEvent.query.filter_by(user_id=user.id).order_by(SecurityEvent.created_at).all()
    return {
        "exported_at": _iso(utcnow()),
        "account": {
            "name": user.name,
            "email": user.email,
            "created_at": _iso(user.created_at),
            "last_login_at": _iso(user.last_login_at),
            "two_step_verification": user.two_factor_enabled,
            "garmin_account": user.garmin_username,
            "spotify_connected": bool(user.spotify_refresh_token),
        },
        "runs": [
            {
                "garmin_activity_id": run.activity_id,
                "started_at": _iso(run.date_time),
                "distance_m": run.distance,
                "duration_s": run.duration,
                "average_heart_rate": run.avg_hr,
                "average_pace_min_per_km": run.avg_pace,
            }
            for run in runs
        ],
        "song_plays_during_runs": [
            {
                "spotify_track_id": play.song_id,
                "track": song.name,
                "artist": song.artist,
                "started_at": _iso(play.played_at),
                "seconds": play.time_played,
                "garmin_activity_id": activity_ids.get(play.run_id),
            }
            for play, song in plays
        ],
        "song_scores": [
            {
                "spotify_track_id": play.song_id,
                "garmin_activity_id": activity_ids.get(analysis.run_id),
                "score": analysis.performance_score,
            }
            for analysis, play in scores
        ],
        "friends": sorted(friend.name for friend in user.friends),
        "security_activity": [
            {
                "event": DESCRIPTIONS.get(e.kind, e.kind),
                "at": _iso(e.created_at),
                "network": e.ip_prefix,
            }
            for e in events
        ],
    }


def _remove_fit_files(user):
    """Delete the user's stored FIT files, touching only files inside the storage folders."""
    storage = Path(current_app.config["FIT_STORAGE_DIR"]).resolve()
    shutil.rmtree(storage / str(user.id), ignore_errors=True)
    legacy_root = Path("fit_files").resolve()  # files saved before per-user folders existed
    for (path,) in db.session.query(Run.fit_file_path).filter(Run.user_id == user.id):
        if not path:
            continue
        candidate = Path(path).resolve()
        if candidate.is_relative_to(legacy_root) and candidate.is_file():
            candidate.unlink()


def delete_account(user):
    """Permanently delete ``user`` and all of their personal data (the caller commits)."""
    _remove_fit_files(user)
    run_ids = db.session.query(Run.id).filter(Run.user_id == user.id)
    db.session.execute(
        delete(RunSongAnalysis).where(
            or_(RunSongAnalysis.user_id == user.id, RunSongAnalysis.run_id.in_(run_ids))
        )
    )
    db.session.execute(delete(UserSongHistory).where(UserSongHistory.user_id == user.id))
    db.session.execute(delete(Run).where(Run.user_id == user.id))
    db.session.execute(
        delete(FriendRequest).where(
            or_(FriendRequest.sender_id == user.id, FriendRequest.receiver_id == user.id)
        )
    )
    db.session.execute(
        delete(friends).where(or_(friends.c.user_id == user.id, friends.c.friend_id == user.id))
    )
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.session.execute(delete(SecurityEvent).where(SecurityEvent.user_id == user.id))
    db.session.delete(user)
