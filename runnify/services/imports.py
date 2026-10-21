"""Background Spotify-history imports.

An upload is saved to a private temporary file, checked, then imported on a
background thread so large histories never hold up a web request. The import
reports its progress as it goes (:mod:`runnify.services.jobs`) and commits a
run at a time while scoring, so pages stay quick and can show how far it has
got. The file is always deleted afterwards, whether the import succeeded or
not; one an interrupted import left behind is swept away by the next upload.
"""

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from flask import current_app

from runnify.extensions import db
from runnify.models import Run, Song, User, UserSongHistory, utcnow
from runnify.services import jobs
from runnify.services.analysis import rescore_run
from runnify.services.history_import import (
    HistoryArchiveError,
    import_history_zip_overlapping_runs,
    inspect_archive,
)
from runnify.services.laps import UsualPaces, retype_runs

logger = logging.getLogger(__name__)

LEFT_BEHIND = 6 * 60 * 60  # seconds; an upload this old belongs to no running import


def save_upload(file_storage):
    """Stream an uploaded file to a private temporary file and return its path."""
    directory = Path(current_app.config["UPLOAD_TMP_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    _sweep(directory)
    handle, path = tempfile.mkstemp(suffix=".zip", dir=directory)
    os.close(handle)
    file_storage.save(path)
    return path


def _sweep(directory):
    """Delete uploads that imports interrupted by a restart never got to delete."""
    cutoff = time.time() - LEFT_BEHIND
    for path in directory.glob("*.zip"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:  # gone already, or still being written
            continue


def check_upload(path):
    """Validate a saved upload as a Spotify history archive (raises ``HistoryArchiveError``)."""
    config = current_app.config
    inspect_archive(
        path,
        max_entries=config["HISTORY_MAX_ENTRIES"],
        max_uncompressed_bytes=config["HISTORY_MAX_UNCOMPRESSED_MB"] * 1024 * 1024,
        max_ratio=config["HISTORY_MAX_COMPRESSION_RATIO"],
    )


def discard(path):
    """Delete an uploaded file, ignoring one that is already gone."""
    Path(path).unlink(missing_ok=True)


def _rescore(user_id, run_ids, progress):
    """Score the songs on each run that gained plays, committing a run at a time.

    Returns:
        How many song plays received a score.
    """
    paces, run_ids = UsualPaces.for_runner(user_id), sorted(run_ids)
    scored = 0
    for done, run_id in enumerate(run_ids, 1):
        scored += rescore_run(db.session.get(Run, run_id), usual=paces.excluding(run_id))
        db.session.commit()
        progress.report(
            f"Scoring the songs on your runs: {done:,} of {len(run_ids):,}", done, len(run_ids)
        )
    return scored


def run_import(user_id, path):
    """Import a checked upload for ``user_id``, record the outcome and delete the file."""
    progress = jobs.Progress(user_id, "history")
    progress.report("Reading your listening history", 0, None, force=True)
    try:
        stats = import_history_zip_overlapping_runs(
            zip_file=path,
            user_id=user_id,
            db=db,
            RunModel=Run,
            SongModel=Song,
            UserSongHistoryModel=UserSongHistory,
            batch_size=current_app.config["HISTORY_BATCH_SIZE"],
            min_overlap_seconds=current_app.config["HISTORY_MIN_OVERLAP_SECONDS"],
            progress=lambda read, size: progress.report(
                f"Reading your listening history: {100 * read // max(size, 1)}%",
                read // 1024,
                max(size // 1024, 1),
            ),
        )
        scored = _rescore(user_id, stats["run_ids"], progress)
        retype_runs(user_id)
        db.session.commit()
    except HistoryArchiveError as error:
        db.session.rollback()
        jobs.end(db.session.get(User, user_id), "history", "failed", str(error))
    except Exception:
        logger.exception("History import failed for user %s", user_id)
        db.session.rollback()
        jobs.end(
            db.session.get(User, user_id),
            "history",
            "failed",
            "Something went wrong while importing. Please try again.",
        )
    else:
        user, saved = db.session.get(User, user_id), stats["saved"]
        jobs.end(
            user,
            "history",
            "ok",
            stats["note"]
            or (
                f"Matched {saved} song play{'s' if saved != 1 else ''} to your runs "
                f"and scored {scored}."
            ),
        )
        user.history_imported_at = utcnow()
    finally:
        discard(path)
    db.session.commit()


def start_background_import(app, user_id, path):
    """Mark ``user_id``'s import as running and process ``path`` on a background thread."""
    jobs.begin(db.session.get(User, user_id), "history", "Starting the import")
    db.session.commit()

    def work():
        with app.app_context():
            run_import(user_id, path)

    threading.Thread(target=work, name=f"history-import-{user_id}", daemon=True).start()
