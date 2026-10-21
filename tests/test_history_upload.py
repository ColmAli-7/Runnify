"""Uploading Spotify history: archive checks and the background import."""

import io
import json
import pathlib
import zipfile
from datetime import datetime, timedelta

import pytest

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, User, UserSongHistory
from runnify.services import imports
from runnify.services.fit import Series
from runnify.services.history_import import (
    HistoryArchiveError,
    import_history_zip_overlapping_runs,
    inspect_archive,
)
from runnify.services.streams import save_stream

LIMITS = {"max_entries": 10, "max_uncompressed_bytes": 10_000_000, "max_ratio": 100}


def _zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    buffer.seek(0)
    return buffer


def _history(ts="2026-10-01T07:05:00Z"):
    row = {
        "ts": ts,
        "ms_played": 200_000,
        "spotify_track_uri": "spotify:track:abc",
        "master_metadata_track_name": "Song",
        "master_metadata_album_artist_name": "Artist",
    }
    return json.dumps([row])


def test_a_real_looking_export_passes():
    assert inspect_archive(_zip({"Streaming_History_Audio_2026.json": _history()}), **LIMITS) == 1


@pytest.mark.parametrize(
    ("archive", "message"),
    [
        (io.BytesIO(b"definitely not a zip"), "isn't a zip"),
        (lambda: _zip({"notes.txt": "hello"}), "no listening history"),
        (lambda: _zip({f"f{n}.json": "[]" for n in range(11)}), "more files"),
        (lambda: _zip({"bomb.json": "0" * 5_000_000}), "doesn't look like a Spotify export"),
    ],
)
def test_suspicious_archives_are_refused(archive, message):
    with pytest.raises(HistoryArchiveError, match=message):
        inspect_archive(archive() if callable(archive) else archive, **LIMITS)


def test_oversized_archives_are_refused():
    big = _zip({"a.json": json.dumps(["x" * 1000 for _ in range(20_000)])})
    with pytest.raises(HistoryArchiveError, match="too large"):
        inspect_archive(big, **{**LIMITS, "max_ratio": 10_000})


@pytest.fixture
def inline_threads(monkeypatch):
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(imports.threading, "Thread", InlineThread)


def _upload(client, archive, filename="my_spotify_data.zip"):
    return client.post(
        "/import",
        data={"history_zip": (archive, filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _add_run(app, user_id):
    with app.app_context():
        db.session.add(
            Run(
                user_id=user_id,
                activity_id="1",
                date_time=datetime(2026, 10, 1, 7),
                duration=1800,
                distance=5000,
            )
        )
        db.session.commit()


def test_upload_requires_runs_first(auth_client):
    response = _upload(auth_client, _zip({"a.json": _history()}))
    assert b"Sync your runs" in response.data


def test_upload_rejects_non_zip_files(app, auth_client, user):
    _add_run(app, user)
    response = _upload(auth_client, io.BytesIO(b"x"), filename="history.json")
    assert b"Choose the .zip" in response.data


def test_upload_imports_in_the_background_and_deletes_the_file(
    app, auth_client, user, inline_threads
):
    _add_run(app, user)
    response = _upload(auth_client, _zip({"Streaming_History_Audio_2026.json": _history()}))
    assert response.status_code == 200
    with app.app_context():
        account = db.session.get(User, user)
        assert account.history_import_state == "ok"
        assert account.history_import_message == "Matched 1 song play to your runs and scored 0."
        assert UserSongHistory.query.count() == 1
    assert list(pathlib.Path(app.config["UPLOAD_TMP_DIR"]).iterdir()) == []


def test_bad_archives_are_deleted_and_reported(app, auth_client, user):
    _add_run(app, user)
    response = _upload(auth_client, _zip({"bomb.json": "0" * 5_000_000}))
    assert b"look like a Spotify export" in response.data
    assert list(pathlib.Path(app.config["UPLOAD_TMP_DIR"]).iterdir()) == []


def test_the_import_reports_how_far_it_has_got(app, auth_client, user, inline_threads, monkeypatch):
    reports = []
    report = imports.jobs.Progress.report

    def spy(self, message, done=None, total=None, force=False):
        reports.append(message)
        return report(self, message, done, total, force=True)

    monkeypatch.setattr(imports.jobs.Progress, "report", spy)
    _add_run(app, user)
    _upload(auth_client, _zip({"Streaming_History_Audio_2026.json": _history()}))
    assert reports[0] == "Reading your listening history"
    assert "Reading your listening history: 100%" in reports
    assert reports[-1] == "Scoring the songs on your runs: 1 of 1"
    with app.app_context():
        assert imports.jobs.job(db.session.get(User, user), "history").state == "ok"


START = datetime(2026, 10, 1, 7)


def _recorded_run(app, user_id):
    """A 20-minute run at 5:00/km with its samples (and no songs yet); returns its id."""
    with app.app_context():
        run = Run(user_id=user_id, activity_id="9", date_time=START, duration=1200, distance=4000)
        db.session.add(run)
        db.session.flush()
        save_stream(
            run,
            Series(
                timestamps=[START + timedelta(seconds=s) for s in range(1200)],
                heart_rates=[150] * 1200,
                paces=[300.0] * 1200,
            ),
        )
        db.session.commit()
        return run.id


def _song_during_the_run():
    """A three-minute song eight minutes into the run."""
    return _zip({"Streaming_History_Audio_2026.json": _history(ts="2026-10-01T07:11:20Z")})


def test_uploading_again_scores_the_runs_an_interrupted_import_left(
    app, auth_client, user, inline_threads
):
    run_id = _recorded_run(app, user)
    with app.app_context():  # an import stored the plays, then Runnify restarted before scoring
        import_history_zip_overlapping_runs(
            zip_file=_song_during_the_run(),
            user_id=user,
            db=db,
            RunModel=Run,
            SongModel=Song,
            UserSongHistoryModel=UserSongHistory,
        )
        assert db.session.get(Run, run_id).scoring_due and RunSongAnalysis.query.count() == 0
    _upload(auth_client, _song_during_the_run())
    with app.app_context():
        message = db.session.get(User, user).history_import_message
        assert message == "Matched 0 song plays to your runs and scored 1."
        assert not db.session.get(Run, run_id).scoring_due
        assert RunSongAnalysis.query.count() == 1


def test_a_run_that_fails_to_score_waits_for_the_next_import(
    app, auth_client, user, inline_threads, monkeypatch
):
    run_id = _recorded_run(app, user)
    rescore = imports.rescore_run

    def broken(run, *args, **kwargs):
        raise RuntimeError("a bug in scoring")

    monkeypatch.setattr(imports, "rescore_run", broken)
    _upload(auth_client, _song_during_the_run())
    with app.app_context():
        account = db.session.get(User, user)
        assert account.history_import_state == "ok"  # the import itself went through
        assert db.session.get(Run, run_id).scoring_due
    monkeypatch.setattr(imports, "rescore_run", rescore)
    _upload(auth_client, _song_during_the_run())
    with app.app_context():
        assert RunSongAnalysis.query.count() == 1 and not db.session.get(Run, run_id).scoring_due
