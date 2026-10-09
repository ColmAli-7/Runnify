"""Background Spotify-history imports.

An upload is saved to a private temporary file, checked, then imported on a
background thread so large histories never hold up a web request. The file is
always deleted afterwards, whether the import succeeded or not.
"""

import logging
import os
import tempfile
import threading
from pathlib import Path

from flask import current_app

from runnify.extensions import db
from runnify.models import Run, Song, User, UserSongHistory, utcnow
from runnify.services.analysis import rescore_runs
from runnify.services.history_import import (
    HistoryArchiveError,
    import_history_zip_overlapping_runs,
    inspect_archive,
)

logger = logging.getLogger(__name__)


def save_upload(file_storage):
    """Stream an uploaded file to a private temporary file and return its path."""
    directory = Path(current_app.config["UPLOAD_TMP_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    handle, path = tempfile.mkstemp(suffix=".zip", dir=directory)
    os.close(handle)
    file_storage.save(path)
    return path


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


def run_import(user_id, path):
    """Import a checked upload for ``user_id``, record the outcome and delete the file."""
    user = db.session.get(User, user_id)
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
        )
        scored = rescore_runs(stats["run_ids"])
        db.session.commit()
    except HistoryArchiveError as error:
        user.history_import_state, user.history_import_message = "failed", str(error)
    except Exception:
        logger.exception("History import failed for user %s", user_id)
        db.session.rollback()
        user = db.session.get(User, user_id)
        user.history_import_state = "failed"
        user.history_import_message = "Something went wrong while importing. Please try again."
    else:
        saved = stats["saved"]
        user.history_import_state = "ok"
        user.history_import_message = stats["note"] or (
            f"Matched {saved} song play{'s' if saved != 1 else ''} to your runs "
            f"and scored {scored}."
        )
        user.history_imported_at = utcnow()
    finally:
        discard(path)
    db.session.commit()


def start_background_import(app, user_id, path):
    """Mark ``user_id``'s import as running and process ``path`` on a background thread."""
    user = db.session.get(User, user_id)
    user.history_import_state, user.history_import_message = "importing", None
    db.session.commit()

    def work():
        with app.app_context():
            run_import(user_id, path)

    threading.Thread(target=work, name=f"history-import-{user_id}", daemon=True).start()
