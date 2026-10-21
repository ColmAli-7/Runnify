"""Import Spotify extended streaming history and match it against runs.

Archives are checked with :func:`inspect_archive` before anything is parsed
(entry count, total uncompressed size and compression ratio, so a zip bomb is
refused), then streamed with ``ijson`` so multi-hundred-MB histories never
need to fit in memory. Each music play is turned into a ``[start, end)``
interval (Spotify's ``ts`` is when playback *stopped*) and intersected with
the runs it overlaps, found by bisecting the runs' start times rather than
trying every run. Each overlap becomes a ``UserSongHistory`` row, noting
whether the track was skipped, unless the runner already has it.

Everything is read and matched before anything is written, then written in
batches, so the database is never held for long. Only songs that played
during a run join the song catalogue; plays that ran to the end, during a run
or not, teach it each track's length. Scoring happens afterwards, in
:mod:`runnify.services.analysis`.
"""

import datetime as dt
import zipfile
from bisect import bisect_left
from typing import Any

import ijson
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

LOOKUP_CHUNK = 500  # ids per IN (...) query, well under every database's limit


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
    runs = db.session.query(RunModel.id, RunModel.date_time, RunModel.duration).filter(
        RunModel.user_id == user_id
    )
    out = []
    for run_id, started, duration in runs:
        if not started or not duration:
            continue
        out.append((run_id, started, started + dt.timedelta(seconds=int(duration))))
    out.sort(key=lambda t: t[1])
    return out


class _RunTimes:
    """The runner's runs in order of start, to find the ones a play could overlap."""

    def __init__(self, intervals):
        self.intervals = intervals  # (run_id, start, end), sorted by start
        self.starts = [start for _, start, _ in intervals]
        self.longest = max((end - start for _, start, end in intervals), default=dt.timedelta())

    def around(self, start, end):
        """The runs that started before ``end`` and late enough to still be going at ``start``."""
        return self.intervals[
            bisect_left(self.starts, start - self.longest) : bisect_left(self.starts, end)
        ]


def _chunks(items, size=LOOKUP_CHUNK):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i : i + size]


class _Counted:
    """A file that tells ``report`` how many bytes each read took, for progress."""

    def __init__(self, raw, report):
        self.raw, self.report = raw, report

    def read(self, size=-1):
        data = self.raw.read(size)
        self.report(len(data))
        return data


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
    progress=None,
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
        batch_size: How many plays to add before each commit.
        min_overlap_seconds: Plays overlapping a run by less than this are ignored.
        progress: Called as the files are read with ``(bytes read, bytes in all)``
            of the JSON files, unpacked.

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
    runs = _RunTimes(_collect_run_intervals(db, RunModel, user_id))
    if not runs.intervals:
        return {**stats, "note": "User has no runs"}

    History = UserSongHistoryModel
    known = {  # plays the runner already has, so a newer upload only adds what's new
        tuple(row)
        for row in db.session.query(History.song_id, History.run_id, History.played_at).filter(
            History.user_id == user_id, History.run_id.isnot(None)
        )
    }
    plays = []
    names = {}  # track id -> (track, artist), as first seen
    lengths = {}  # track id -> longest complete play, in seconds

    with zipfile.ZipFile(zip_file) as zf:
        stats["files"] = len(zf.namelist())
        entries = [e for e in zf.infolist() if e.filename.lower().endswith(".json")]
        size, read = sum(e.file_size for e in entries), 0

        def counted(length):
            nonlocal read
            read += length
            if progress:
                progress(read, size)

        for entry in entries:
            stats["json_files"] += 1
            with zf.open(entry, "r") as f:
                for row in _iter_json_rows(_Counted(f, counted)):
                    stats["rows"] += 1
                    track_id = None if _is_podcast_or_video(row) else _spotify_track_id(row)
                    interval = _row_interval(row) if track_id else None
                    if not interval:
                        stats["ignored"] += 1
                        continue
                    if (length := _full_length_seconds(row)) is not None:
                        lengths[track_id] = max(length, lengths.get(track_id, 0))
                    if track_id not in names:
                        names[track_id] = _names(row)[:2]

                    play_start, play_end = interval
                    skipped = _was_skipped(row)
                    for run_id, run_start, run_end in runs.around(play_start, play_end):
                        overlap = _overlap(play_start, play_end, run_start, run_end)
                        if not overlap:
                            continue
                        seg_start, seg_end = overlap
                        seconds = _seconds(seg_end - seg_start)
                        key = (track_id, run_id, seg_start)
                        if seconds < min_overlap_seconds or key in known:
                            continue
                        known.add(key)
                        plays.append(
                            {
                                "user_id": user_id,
                                "song_id": track_id,
                                "played_at": seg_start,
                                "time_played": seconds,
                                "run_id": run_id,
                                "skipped": skipped,
                            }
                        )
                        stats["saved"] += 1
                        stats["skipped_during_runs"] += bool(skipped)
                        stats["run_ids"].add(run_id)

    for batch in _chunks(plays, batch_size):
        # only songs that played during a run join the catalogue, each committed with the
        # plays that use it, so a clean-up of unused songs can never see it unused
        for attempt in (1, 2):
            try:
                _add_songs(
                    db, SongModel, {play["song_id"]: names[play["song_id"]] for play in batch}
                )
                db.session.execute(insert(History), batch)
                db.session.commit()
                break
            except IntegrityError:  # another runner's import added one of the songs just now
                db.session.rollback()
                stats["errors"] += attempt == 2
            except Exception:
                db.session.rollback()
                stats["errors"] += 1
                break
    _learn_lengths(db, SongModel, lengths)
    return stats


def _add_songs(db, SongModel, names):
    """Add the tracks in ``names`` (``{track id: (track, artist)}``) the catalogue lacks.

    The caller commits, together with the plays that use them.
    """
    existing = set()
    for chunk in _chunks(names):
        existing.update(db.session.scalars(select(SongModel.id).where(SongModel.id.in_(chunk))))
    missing = [
        {
            "id": track_id,
            "name": track,
            "artist": artist,
            "spotify_url": f"https://open.spotify.com/track/{track_id}",
        }
        for track_id, (track, artist) in names.items()
        if track_id not in existing
    ]
    for chunk in _chunks(missing):
        db.session.execute(insert(SongModel), chunk)


def _learn_lengths(db, SongModel, lengths):
    """Give catalogue songs the longest complete play heard of them, when that is longer."""
    longer = []
    for chunk in _chunks(lengths):
        rows = db.session.execute(
            select(SongModel.id, SongModel.duration).where(SongModel.id.in_(chunk))
        )
        longer += [
            {"id": track_id, "duration": lengths[track_id]}
            for track_id, duration in rows
            if (duration or 0) < lengths[track_id]
        ]
    if longer:
        db.session.execute(update(SongModel), longer)
    db.session.commit()
