"""Tests for importing a Spotify extended streaming history zip."""

import io
import json
import zipfile
from datetime import datetime

from runnify.extensions import db
from runnify.models import Run, Song, User, UserSongHistory
from runnify.services.history_import import import_history_zip_overlapping_runs


def _history_zip(rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "Spotify Extended Streaming History/Streaming_History_Audio_2026.json", json.dumps(rows)
        )
        archive.writestr("ReadMeFirst.pdf", b"not json")
    return buffer.getvalue()


def _row(ts, ms, uri, name="Track", artist="Artist", **extra):
    return {
        "ts": ts,
        "ms_played": ms,
        "spotify_track_uri": uri,
        "master_metadata_track_name": name,
        "master_metadata_album_artist_name": artist,
        "master_metadata_album_album_name": "Album",
        **extra,
    }


def test_import_links_overlapping_music_and_skips_the_rest(app):
    rows = [
        _row(
            "2026-10-01T07:05:00Z", 200_000, "spotify:track:during"
        ),  # 07:01:40-07:05:00, inside the run
        _row("2026-10-01T06:00:00Z", 180_000, "spotify:track:before"),  # an hour before the run
        _row("2026-10-01T07:10:00Z", 60_000, None, episode_name="A podcast"),  # podcast
        _row("2026-10-01T07:12:00Z", 60_000, None),  # no track uri
    ]
    with app.app_context():
        user = User(name="T", email="t@example.com", password_hash="x")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Run(
                user_id=user.id,
                activity_id="1",
                date_time=datetime(2026, 10, 1, 7),
                duration=1800,
                distance=5000,
            )
        )
        db.session.commit()

        stats = import_history_zip_overlapping_runs(
            zip_file=io.BytesIO(_history_zip(rows)),
            user_id=user.id,
            db=db,
            RunModel=Run,
            SongModel=Song,
            UserSongHistoryModel=UserSongHistory,
        )

        assert stats["json_files"] == 1
        assert stats["rows"] == 4
        assert stats["saved"] == 1
        assert stats["ignored"] == 2
        assert stats["run_ids"] == {1}
        play = UserSongHistory.query.one()
        assert play.song_id == "during"
        assert play.played_at == datetime(2026, 10, 1, 7, 1, 40)
        assert play.time_played == 200


def test_import_without_runs_does_nothing(app):
    with app.app_context():
        user = User(name="T", email="t@example.com", password_hash="x")
        db.session.add(user)
        db.session.commit()
        stats = import_history_zip_overlapping_runs(
            zip_file=io.BytesIO(
                _history_zip([_row("2026-10-01T07:05:00Z", 200_000, "spotify:track:x")])
            ),
            user_id=user.id,
            db=db,
            RunModel=Run,
            SongModel=Song,
            UserSongHistoryModel=UserSongHistory,
        )
        assert stats["note"] == "User has no runs"
        assert UserSongHistory.query.count() == 0


def test_import_records_skips_and_learns_track_lengths(app):
    rows = [
        _row("2026-10-01T07:05:00Z", 200_000, "spotify:track:full", reason_end="trackdone"),
        _row("2026-10-01T07:06:00Z", 20_000, "spotify:track:skip", reason_end="fwdbtn"),
    ]
    with app.app_context():
        user = User(name="T", email="t@example.com", password_hash="x")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Run(
                user_id=user.id,
                activity_id="1",
                date_time=datetime(2026, 10, 1, 7),
                duration=1800,
                distance=5000,
            )
        )
        db.session.commit()
        stats = import_history_zip_overlapping_runs(
            zip_file=io.BytesIO(_history_zip(rows)),
            user_id=user.id,
            db=db,
            RunModel=Run,
            SongModel=Song,
            UserSongHistoryModel=UserSongHistory,
        )
        assert stats["skipped_during_runs"] == 1
        plays = {p.song_id: p.skipped for p in UserSongHistory.query}
        assert plays == {"full": False, "skip": True}
        assert db.session.get(Song, "full").duration == 200
        assert db.session.get(Song, "skip").duration is None


def _import(rows, runs):
    """Import ``rows`` for a new user with ``runs`` (``(start, seconds)``); returns the stats."""
    user = User(name="T", email="t@example.com", password_hash="x")
    db.session.add(user)
    db.session.flush()
    for n, (start, seconds) in enumerate(runs):
        db.session.add(
            Run(
                user_id=user.id,
                activity_id=str(n),
                date_time=start,
                duration=seconds,
                distance=5000,
            )
        )
    db.session.commit()
    return import_history_zip_overlapping_runs(
        zip_file=io.BytesIO(_history_zip(rows)),
        user_id=user.id,
        db=db,
        RunModel=Run,
        SongModel=Song,
        UserSongHistoryModel=UserSongHistory,
    )


def test_only_songs_played_during_a_run_join_the_catalogue(app):
    rows = [
        _row("2026-10-01T07:05:00Z", 200_000, "spotify:track:during"),
        _row("2026-10-01T06:00:00Z", 180_000, "spotify:track:before", reason_end="trackdone"),
        # a complete play of the run's song, the day before, still teaches its length
        _row("2026-09-30T18:00:00Z", 215_000, "spotify:track:during", reason_end="trackdone"),
    ]
    with app.app_context():
        _import(rows, [(datetime(2026, 10, 1, 7), 1800)])
        assert [(song.id, song.duration) for song in Song.query] == [("during", 215)]


def test_a_play_listed_twice_is_stored_once(app):
    row = _row("2026-10-01T07:05:00Z", 200_000, "spotify:track:twice")
    with app.app_context():
        stats = _import([row, dict(row)], [(datetime(2026, 10, 1, 7), 1800)])
        assert stats["saved"] == 1 and UserSongHistory.query.count() == 1


def test_a_play_is_linked_to_every_recording_of_the_run_it_overlapped(app):
    rows = [_row("2026-10-01T07:05:00Z", 200_000, "spotify:track:both")]
    runs = [(datetime(2026, 10, 1, 7), 1800), (datetime(2026, 10, 1, 7, 2), 1500)]  # two watches
    with app.app_context():
        stats = _import(rows, runs)
        first, second = sorted(stats["run_ids"])
        plays = sorted((p.run_id, p.played_at, p.time_played) for p in UserSongHistory.query)
        assert plays == [
            (first, datetime(2026, 10, 1, 7, 1, 40), 200),
            (second, datetime(2026, 10, 1, 7, 2), 180),  # the part after the second watch started
        ]
