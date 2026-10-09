"""Tests for importing a Spotify extended streaming history zip."""

import io
import json
import zipfile
from datetime import datetime

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, User, UserSongHistory
from runnify.services.fit import Series
from runnify.services.history_import import import_history_zip_overlapping_runs
from runnify.services.scoring import score_segment


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
            RunSongAnalysisModel=RunSongAnalysis,
            read_series=lambda run: Series(),
            score_segment=score_segment,
        )

        assert stats["json_files"] == 1
        assert stats["rows"] == 4
        assert stats["saved"] == 1
        assert stats["skipped"] == 2
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
            RunSongAnalysisModel=RunSongAnalysis,
            read_series=lambda run: Series(),
            score_segment=score_segment,
        )
        assert stats["note"] == "User has no runs"
        assert UserSongHistory.query.count() == 0
