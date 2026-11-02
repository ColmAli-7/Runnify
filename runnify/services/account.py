"""Account data rights: export everything we hold about a user, or delete it all.

The export never includes secrets (password hash, tokens, two-step secrets).
Each run's samples are exported as they are stored, one list a channel. The
runs, plays and scores are read from the database a batch at a time as the
file is written, and each run's stream is decoded only when the file reaches
that run, so writing it takes about the same memory however long the history.
Deletion removes every personal row and the user's stored FIT files, then
any song in the shared catalogue that no one's plays or playlists use any
more, so the catalogue only ever holds songs that played during someone's
runs.
"""

import json
import shutil
from collections.abc import Iterator
from itertools import batched, chain
from pathlib import Path

from flask import current_app
from sqlalchemy import and_, delete, exists, or_

from runnify.extensions import db
from runnify.models import (
    FriendRequest,
    Playlist,
    PlaylistTrack,
    RecoveryCode,
    Run,
    RunLap,
    RunSongAnalysis,
    RunStream,
    SecurityEvent,
    Song,
    UserSongHistory,
    friends,
    utcnow,
)
from runnify.security.audit import DESCRIPTIONS
from runnify.services.streams import decode

RUN_BATCH = 100  # runs whose laps and stored streams are read together
ROW_BATCH = 1000  # plays or scores fetched from the database at a time
CHUNK_SIZE = 64 * 1024  # characters in each piece of a streamed export (all ASCII, so bytes)

_compact = json.JSONEncoder(separators=(",", ":")).encode
_END = object()


def _iso(value):
    return value.isoformat() + "Z" if value else None


def _stream(stream):
    """A run's stored stream for the export: the watch's laps, and the samples as recorded.

    The samples are parallel lists, one a channel, counted in seconds from the
    first sample; a channel the recording didn't have is ``None``.
    """
    series = decode(stream.samples, stream.started_at, spread=False)
    start = stream.started_at
    return {
        "watch_laps": [
            {
                "start_s": lap.start,
                "end_s": lap.end,
                "intensity": lap.intensity,
                "trigger": lap.trigger,
                "workout_step": lap.step,
            }
            for lap in series.laps
        ],
        "samples": {
            "started_at": _iso(start),
            "seconds": [round((t - start).total_seconds()) for t in series.timestamps],
            "pace_s_per_km": series.paces,
            "heart_rate_bpm": series.heart_rates,
            "cadence_steps_per_min": series.cadences or None,
            "distance_m": series.distances or None,
        },
    }


def _runs(user_id):
    """The runs for the export, oldest first, each with its laps and its stored stream if any.

    The runs come a batch at a time with their laps and compressed streams,
    and each stream is decoded only when its run is wanted.
    """
    runs = Run.query.filter_by(user_id=user_id).order_by(Run.date_time).yield_per(RUN_BATCH)
    for batch in batched(runs, RUN_BATCH, strict=False):
        ids = [run.id for run in batch]
        laps = {}
        for lap in RunLap.query.filter(RunLap.run_id.in_(ids)).order_by(RunLap.position):
            laps.setdefault(lap.run_id, []).append(
                {
                    "kind": lap.kind,
                    "start_s": lap.start_second,
                    "end_s": lap.end_second,
                    "distance_m": lap.distance,
                    "moving_time_s": lap.moving_seconds,
                    "average_heart_rate": lap.avg_hr,
                }
            )
        streams = {
            stream.run_id: stream for stream in RunStream.query.filter(RunStream.run_id.in_(ids))
        }
        for run in batch:
            stream = streams.pop(run.id, None)
            yield {
                "garmin_activity_id": run.activity_id,
                "started_at": _iso(run.date_time),
                "utc_offset_minutes": run.utc_offset,
                "distance_m": run.distance,
                "duration_s": run.duration,
                "average_heart_rate": run.avg_hr,
                "average_pace_min_per_km": run.avg_pace,
                "run_type": run.run_type,
                "run_type_set_by_you": run.run_type_manual,
                "laps": laps.get(run.id, []),
                "laps_source": run.laps_source,
                "workout": run.workout,
                **(_stream(stream) if stream is not None else {}),
            }


def _plays(user_id):
    """The song plays for the export, in the order they played, a batch at a time."""
    plays = (
        db.session.query(UserSongHistory, Song, Run.activity_id)
        .join(Song, Song.id == UserSongHistory.song_id)
        .outerjoin(Run, and_(Run.id == UserSongHistory.run_id, Run.user_id == user_id))
        .filter(UserSongHistory.user_id == user_id)
        .order_by(UserSongHistory.played_at)
        .yield_per(ROW_BATCH)
    )
    for play, song, activity_id in plays:
        yield {
            "spotify_track_id": play.song_id,
            "track": song.name,
            "artist": song.artist,
            "started_at": _iso(play.played_at),
            "seconds": play.time_played,
            "skipped": play.skipped,
            "garmin_activity_id": activity_id,
        }


def _scores(user_id):
    """The song scores for the export, in the order they were made, a batch at a time."""
    scores = (
        db.session.query(RunSongAnalysis, UserSongHistory, Run.activity_id)
        .join(UserSongHistory, UserSongHistory.id == RunSongAnalysis.user_song_id)
        .outerjoin(Run, and_(Run.id == RunSongAnalysis.run_id, Run.user_id == user_id))
        .filter(RunSongAnalysis.user_id == user_id)
        .order_by(RunSongAnalysis.id)
        .yield_per(ROW_BATCH)
    )
    for analysis, play, activity_id in scores:
        yield {
            "spotify_track_id": play.song_id,
            "garmin_activity_id": activity_id,
            "score": analysis.performance_score,
            "lift_s_per_km": analysis.pace_delta,
            "heart_rate_change_bpm": analysis.hr_delta,
            "lap_kind": analysis.lap_kind,
            "effort_charge_s_per_km": analysis.effort_charge,
        }


def export_data(user):
    """Return everything Runnify stores about ``user``, for :func:`to_json` or :func:`json_chunks`.

    The runs, song plays and song scores grow with the runner's history, so
    they are generators that read the database only as the file is written;
    the rest is read now. The generators go by ``user``'s id alone: by the
    time a streamed response reads them, its view has committed and Flask
    has closed the session that loaded ``user``.
    """
    user_id = user.id
    events = SecurityEvent.query.filter_by(user_id=user_id).order_by(SecurityEvent.created_at).all()
    waiting = FriendRequest.query.filter_by(status="pending").order_by(FriendRequest.timestamp)
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
            "consent": {
                "terms_accepted_at": _iso(user.terms_accepted_at),
                "data_consent_at": _iso(user.data_consent_at),
                "policy_version": user.policy_version,
            },
        },
        "runs": _runs(user_id),
        "song_plays_during_runs": _plays(user_id),
        "song_scores": _scores(user_id),
        "playlists": [
            {
                "name": playlist.name,
                "session": playlist.session,
                "target_minutes": playlist.target_minutes,
                "created_at": _iso(playlist.created_at),
                "spotify_url": playlist.spotify_url,
                "spotify_track_ids": [track.song_id for track in playlist.tracks],
            }
            for playlist in Playlist.query.filter_by(user_id=user.id).order_by(Playlist.created_at)
        ],
        "friends": sorted(friend.name for friend in user.friends),
        "friend_requests": {  # those still waiting for a reply; accepted ones are in friends
            "sent": [
                {"to": r.receiver.name, "sent_at": _iso(r.timestamp)}
                for r in waiting.filter_by(sender_id=user_id)
            ],
            "received": [
                {"from": r.sender.name, "sent_at": _iso(r.timestamp)}
                for r in waiting.filter_by(receiver_id=user_id)
            ],
        },
        "security_activity": [
            {
                "event": DESCRIPTIONS.get(e.kind, e.kind),
                "at": _iso(e.created_at),
                "browser": e.user_agent,
                "network": e.ip_prefix,
            }
            for e in events
        ],
    }


def to_json(value):
    """``value`` as JSON indented two spaces a level, with each list of plain values on one line.

    Objects and lists of objects get a line an item. A run's samples run to
    thousands of numbers a channel, and a line each keeps the file readable
    and about a third of the size of a number a line. A list may also be
    given as an iterator, which is read as it is written.
    """
    return "".join(_pieces(value))


def json_chunks(value):
    """Yield :func:`to_json`'s text for ``value`` in pieces of about :data:`CHUNK_SIZE` characters.

    For a streamed response: ``value``'s iterators are only read as the text
    reaches them, and the closing brackets come last, so a download cut short
    is never valid JSON.
    """
    pieces, size = [], 0
    for piece in _pieces(value):
        pieces.append(piece)
        size += len(piece)
        if size >= CHUNK_SIZE:
            yield "".join(pieces)
            pieces, size = [], 0
    if pieces:
        yield "".join(pieces)


def _pieces(value, depth=0):
    """Yield :func:`to_json`'s text for ``value``, ``depth`` levels in, piece by piece."""
    if isinstance(value, dict) and value:
        items = ((f"{json.dumps(key)}: ", item) for key, item in value.items())
        opening, closing = "{", "}"
    elif isinstance(value, list | Iterator):
        rest = iter(value)
        first = next(rest, _END)
        if first is _END:
            yield "[]"
            return
        if not isinstance(first, dict | list | Iterator):  # plain values: one line
            yield _compact([first, *rest])
            return
        items = (("", item) for item in chain([first], rest))
        opening, closing = "[", "]"
    else:
        yield _compact(value)
        return
    indent = "\n" + "  " * (depth + 1)
    yield opening
    for n, (label, item) in enumerate(items):
        yield ("," if n else "") + indent + label
        yield from _pieces(item, depth + 1)
    yield "\n" + "  " * depth + closing


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
    playlist_ids = db.session.query(Playlist.id).filter(Playlist.user_id == user.id)
    songs = {  # theirs, to see which no one else uses once they are gone
        song_id
        for (song_id,) in db.session.query(UserSongHistory.song_id)
        .filter(UserSongHistory.user_id == user.id)
        .union(
            db.session.query(PlaylistTrack.song_id).filter(
                PlaylistTrack.playlist_id.in_(playlist_ids)
            )
        )
        if song_id is not None
    }
    run_ids = db.session.query(Run.id).filter(Run.user_id == user.id)
    db.session.execute(
        delete(RunSongAnalysis).where(
            or_(RunSongAnalysis.user_id == user.id, RunSongAnalysis.run_id.in_(run_ids))
        )
    )
    db.session.execute(delete(RunStream).where(RunStream.run_id.in_(run_ids)))
    db.session.execute(delete(RunLap).where(RunLap.run_id.in_(run_ids)))
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
    db.session.execute(delete(PlaylistTrack).where(PlaylistTrack.playlist_id.in_(playlist_ids)))
    db.session.execute(delete(Playlist).where(Playlist.user_id == user.id))
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.session.execute(delete(SecurityEvent).where(SecurityEvent.user_id == user.id))
    remove_unused_songs(songs)
    db.session.delete(user)


def remove_unused_songs(song_ids):
    """Delete those of ``song_ids`` that no play and no playlist uses any more (the caller commits).

    Each song is looked up through the plays' index on their song, so this
    stays quick however many plays there are.
    """
    song_ids = sorted(song_ids)
    for start in range(0, len(song_ids), 500):
        db.session.execute(
            delete(Song).where(
                Song.id.in_(song_ids[start : start + 500]),
                ~exists().where(UserSongHistory.song_id == Song.id),
                ~exists().where(PlaylistTrack.song_id == Song.id),
            )
        )
