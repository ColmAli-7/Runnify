"""Import Spotify extended streaming history and match it against runs.

Archives are checked with :func:`inspect_archive` before anything is parsed
(entry count, total uncompressed size and compression ratio, so a zip bomb is
refused), then streamed with ``ijson`` so multi-hundred-MB histories never
need to fit in memory. Each music play is turned into a ``[start, end)``
interval (Spotify's ``ts`` is when playback *stopped*), intersected with every
run interval, and stored as ``UserSongHistory`` rows, noting whether the track
was skipped. Plays that ran to the end teach the catalogue each track's length.
Scoring happens afterwards, in :mod:`runnify.services.analysis`.
"""

import datetime as dt
import zipfile
from typing import Any

import ijson


class HistoryArchiveError(ValueError):
    """The upload isn't a usable Spotify history archive (the message is safe to show)."""


def inspect_archive(zip_file, *, max_entries, max_uncompressed_bytes, max_ratio):
    """Check an uploaded archive before parsing it.

    Args:
        zip_file: Path or seekable binary file of the upload.
        max_entries: Most entries an archive may contain.
        max_uncompressed_bytes: Largest total size of the JSON entries once unpacked.
        max_ratio: Highest compression ratio allowed for any entry.

    Returns:
        The number of JSON entries.

    Raises:
        HistoryArchiveError: The file is not a zip, holds no JSON, is encrypted,
            or is far bigger unpacked than any real export (a zip bomb).
    """
    try:
        with zipfile.ZipFile(zip_file) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError) as error:
        raise HistoryArchiveError("That file isn't a zip archive.") from error
    if len(entries) > max_entries:
        raise HistoryArchiveError("That archive has far more files than a Spotify export.")
    json_entries = [e for e in entries if e.filename.lower().endswith(".json")]
    if not json_entries:
        raise HistoryArchiveError("That archive has no listening history (.json) files in it.")
    if any(e.flag_bits & 0x1 for e in json_entries):
        raise HistoryArchiveError("That archive is password-protected.")
    if sum(e.file_size for e in json_entries) > max_uncompressed_bytes:
        raise HistoryArchiveError("That archive is too large once unpacked.")
    for entry in json_entries:
        if entry.compress_size and entry.file_size / entry.compress_size > max_ratio:
            raise HistoryArchiveError("That archive doesn't look like a Spotify export.")
    return len(json_entries)


def _parse_ts_stop_utc(ts_str: str):
    """Parse a Spotify ``ts`` value into a naive UTC ``datetime`` (``None`` if invalid)."""
    if not ts_str:
        return None
    try:
        return dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            if ts_str.endswith("Z"):
                d = dt.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                return d.astimezone(dt.UTC).replace(tzinfo=None)
            d = dt.datetime.fromisoformat(ts_str)
            return d.astimezone(dt.UTC).replace(tzinfo=None)
        except Exception:
            return None


def _row_interval(row: dict[str, Any]):
    """Return the ``(start, end)`` interval of a play, using ``ts - ms_played`` as start."""
    ts = _parse_ts_stop_utc(row.get("ts"))
    if ts is None:
        return None
    ms = row.get("ms_played")
    try:
        ms = int(ms) if ms is not None else 0
    except Exception:
        ms = 0
    start = ts - dt.timedelta(milliseconds=ms)
    end = ts
    return (start, end) if start < end else None


def _is_podcast_or_video(row: dict[str, Any]):
    """Return ``True`` if the row is a podcast episode or video rather than music."""
    return bool(
        row.get("episode_name") or row.get("episode_show_name") or row.get("spotify_episode_uri")
    )


def _spotify_track_id(row: dict[str, Any]):
    """Extract the track id from a ``spotify:track:<id>`` URI (``None`` if absent)."""
    uri = row.get("spotify_track_uri")
    if not uri:
        return None
    parts = uri.split(":")
    if len(parts) >= 3 and parts[1] == "track":
        return parts[2]
    return None


def _names(row: dict[str, Any]):
    """Return ``(track, artist, album)`` names from a history row."""
    return (
        row.get("master_metadata_track_name"),
        row.get("master_metadata_album_artist_name"),
        row.get("master_metadata_album_album_name"),
    )


def _overlap(a_start: dt.datetime, a_end: dt.datetime, b_start: dt.datetime, b_end: dt.datetime):
    """Return the overlapping ``(start, end)`` of two intervals, or ``None``."""
    s = max(a_start, b_start)
    e = min(a_end, b_end)
    return (s, e) if s < e else None


def _seconds(td: dt.timedelta):
    """Return a timedelta as whole, non-negative seconds."""
    return max(0, int(td.total_seconds()))  # ensures no negative values


def _collect_run_intervals(db, RunModel, user_id: int):
    """Return the user's runs as ``(run_id, start, end)`` tuples sorted by start time."""
    runs = db.session.query(RunModel).filter(RunModel.user_id == user_id).all()
    out = []
    for r in runs:
        if not r.date_time or not r.duration:
            continue
        start = r.date_time
        end = r.date_time + dt.timedelta(seconds=int(r.duration))
        out.append((r.id, start, end))
    out.sort(key=lambda t: t[1])
    return out


def _iter_json_rows(file_like):
    """Stream the dict items of a top-level JSON array, stopping quietly on bad JSON."""
    try:
        for row in ijson.items(file_like, "item"):
            if isinstance(row, dict):
                yield row
    except ijson.JSONError:
        return


def _was_skipped(row: dict[str, Any]):
    """``True``/``False`` when the export says whether the track was skipped, else ``None``."""
    if row.get("skipped") is True or row.get("reason_end") == "fwdbtn":
        return True
    if row.get("reason_end") == "trackdone":
        return False
    return row.get("skipped")


def _full_length_seconds(row: dict[str, Any]):
    """The track's length when this play ran to the end (``None`` otherwise)."""
    if row.get("reason_end") != "trackdone":
        return None
    try:
        seconds = int(row.get("ms_played") or 0) // 1000
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 30 else None


def import_history_zip_overlapping_runs(
    *,
    zip_file,
    user_id: int,
    db,
    RunModel,
    SongModel,
    UserSongHistoryModel,
    batch_size: int = 500,
    min_overlap_seconds: int = 1,
):
    """Import a Spotify history zip and link each music play to the runs it overlapped.

    Scoring is a separate step (:mod:`runnify.services.analysis`). Models are
    injected so this module stays free of app imports.

    Args:
        zip_file: Path or seekable binary file of the ``my_spotify_data.zip``
            export, already checked with :func:`inspect_archive`.
        user_id: The user the history belongs to.
        db: Flask-SQLAlchemy ``db`` instance.
        RunModel, SongModel, UserSongHistoryModel: The model classes to use.
        batch_size: How many rows to add before each commit.
        min_overlap_seconds: Plays overlapping a run by less than this are ignored.

    Returns:
        A stats dict: ``files``, ``json_files``, ``rows``, ``saved`` (plays linked to
        runs), ``ignored`` (podcasts, videos, unusable rows), ``skipped_during_runs``,
        ``errors``, ``run_ids`` (runs that gained plays) and an optional ``note``.
    """
    stats = {
        "files": 0,
        "json_files": 0,
        "rows": 0,
        "saved": 0,
        "ignored": 0,
        "skipped_during_runs": 0,
        "errors": 0,
        "run_ids": set(),
        "note": None,
    }
    run_intervals = _collect_run_intervals(db, RunModel, user_id)
    if not run_intervals:
        return {**stats, "note": "User has no runs"}

    pending = []
    seen_songs = set()
    lengths = {}  # track id -> longest complete play, in seconds

    def flush():
        if not pending:
            return
        try:
            db.session.add_all(pending)
            db.session.commit()
        except Exception:
            db.session.rollback()
            stats["errors"] += 1
        pending.clear()

    with zipfile.ZipFile(zip_file) as zf:
        names = zf.namelist()
        stats["files"] = len(names)
        for name in names:
            if not name.lower().endswith(".json"):
                continue
            stats["json_files"] += 1
            with zf.open(name, "r") as f:
                for row in _iter_json_rows(f):
                    stats["rows"] += 1
                    track_id = None if _is_podcast_or_video(row) else _spotify_track_id(row)
                    interval = _row_interval(row) if track_id else None
                    if not interval:
                        stats["ignored"] += 1
                        continue
                    if (length := _full_length_seconds(row)) is not None:
                        lengths[track_id] = max(length, lengths.get(track_id, 0))
                    if track_id not in seen_songs:  # make sure the track is in the catalogue
                        seen_songs.add(track_id)
                        if not db.session.get(SongModel, track_id):
                            track, artist, _album = _names(row)
                            db.session.add(
                                SongModel(
                                    id=track_id,
                                    name=track,
                                    artist=artist,
                                    spotify_url=f"https://open.spotify.com/track/{track_id}",
                                )
                            )

                    play_start, play_end = interval
                    skipped = _was_skipped(row)
                    for run_id, run_start, run_end in run_intervals:
                        overlap = _overlap(play_start, play_end, run_start, run_end)
                        if not overlap:
                            continue
                        seg_start, seg_end = overlap
                        seconds = _seconds(seg_end - seg_start)
                        if seconds < min_overlap_seconds:
                            continue
                        already = (
                            db.session.query(UserSongHistoryModel.id)
                            .filter_by(
                                user_id=user_id,
                                song_id=track_id,
                                run_id=run_id,
                                played_at=seg_start,
                            )
                            .first()
                        )
                        if already:
                            continue
                        pending.append(
                            UserSongHistoryModel(
                                user_id=user_id,
                                song_id=track_id,
                                played_at=seg_start,
                                time_played=seconds,
                                run_id=run_id,
                                skipped=skipped,
                            )
                        )
                        stats["saved"] += 1
                        stats["skipped_during_runs"] += bool(skipped)
                        stats["run_ids"].add(run_id)
                        if len(pending) >= batch_size:
                            flush()
    flush()

    for track_id, length in lengths.items():  # learn track lengths for playlist building
        song = db.session.get(SongModel, track_id)
        if song is not None and (song.duration or 0) < length:
            song.duration = length
    db.session.commit()
    return stats
