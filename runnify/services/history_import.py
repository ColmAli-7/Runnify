"""Import Spotify extended streaming history and match it against runs.

Archives are checked with :func:`inspect_archive` before anything is parsed
(entry count, total uncompressed size and compression ratio, so a zip bomb is
refused), then streamed with ``ijson`` so multi-hundred-MB histories never
need to fit in memory. Each music play is turned into a ``[start, end)``
interval (Spotify's ``ts`` is when playback *stopped*), intersected with every
run interval, and stored as ``UserSongHistory`` rows. Performance scores are
then computed per play and stored as ``RunSongAnalysis`` rows.
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


def import_history_zip_overlapping_runs(
    *,
    zip_file,
    user_id: int,
    db,
    RunModel,
    SongModel,
    UserSongHistoryModel,
    RunSongAnalysisModel,
    read_series,
    score_segment,
    batch_size: int = 500,
    min_overlap_seconds: int = 1,
):
    """Import a Spotify history zip, link plays to runs and score them.

    Models and helpers are injected so this module stays free of app imports.

    Args:
        zip_file: Path or seekable binary file of the ``my_spotify_data.zip``
            export, already checked with :func:`inspect_archive`.
        user_id: The user the history belongs to.
        db: Flask-SQLAlchemy ``db`` instance.
        RunModel, SongModel, UserSongHistoryModel, RunSongAnalysisModel:
            The model classes to read and write.
        read_series: Callable returning a run's :class:`~runnify.services.fit.Series`
            of samples (empty when none were recorded).
        score_segment: Callable that scores one song segment of a run.
        batch_size: How many rows to add before each commit.
        min_overlap_seconds: Plays overlapping a run by less than this are
            ignored.

    Returns:
        A stats dict with counts for ``files``, ``json_files``, ``rows``,
        ``saved``, ``skipped`` and ``errors``, plus an optional ``note``.
    """
    stats = {
        "files": 0,
        "json_files": 0,
        "rows": 0,
        "saved": 0,
        "skipped": 0,
        "errors": 0,
        "note": None,
    }
    run_intervals = _collect_run_intervals(db, RunModel, user_id)
    if not run_intervals:
        return {**stats, "note": "User has no runs"}

    run_data_cache = {}  # store fit data to avoid rereading
    user_songs_to_add = []
    seen_songs = set()

    # process all spotify json files in the uploaded zip
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
                    if _is_podcast_or_video(row):  # ignore podcasts
                        stats["skipped"] += 1
                        continue
                    track_id = _spotify_track_id(row)
                    if not track_id:  # ignore missing track ids
                        stats["skipped"] += 1
                        continue
                    iv = _row_interval(row)
                    if not iv:
                        stats["skipped"] += 1
                        continue
                    ev_start, ev_end = iv

                    # ensure track exists in db
                    if track_id not in seen_songs:
                        seen_songs.add(track_id)
                        if not db.session.get(SongModel, track_id):
                            track, artist, _album = _names(row)
                            db.session.add(
                                SongModel(
                                    id=track_id,
                                    name=track,
                                    artist=artist,
                                    duration=None,
                                    spotify_url=f"https://open.spotify.com/track/{track_id}",
                                    tempo=None,
                                )
                            )

                    # check overlap between song playback and each run
                    for run_id, run_start, run_end in run_intervals:
                        ov = _overlap(ev_start, ev_end, run_start, run_end)
                        if not ov:
                            continue
                        seg_start, seg_end = ov
                        secs = _seconds(seg_end - seg_start)
                        if secs < min_overlap_seconds:
                            continue
                        exists = (
                            db.session.query(UserSongHistoryModel.id)
                            .filter_by(
                                user_id=user_id,
                                song_id=track_id,
                                run_id=run_id,
                                played_at=seg_start,
                            )
                            .first()
                        )
                        if exists:
                            continue
                        user_songs_to_add.append(
                            UserSongHistoryModel(
                                user_id=user_id,
                                song_id=track_id,
                                played_at=seg_start,
                                time_played=secs,
                                run_id=run_id,
                            )
                        )
                        stats["saved"] += 1
                        if len(user_songs_to_add) >= batch_size:
                            try:
                                db.session.add_all(user_songs_to_add)
                                db.session.commit()
                                user_songs_to_add.clear()
                            except Exception:
                                db.session.rollback()
                                stats["errors"] += 1

    # commit remaining song entries
    if user_songs_to_add:
        try:
            db.session.add_all(user_songs_to_add)
            db.session.commit()
        except Exception:
            db.session.rollback()
            stats["errors"] += 1

    # calculate performance scores per song-run pair
    try:
        for run_id, _, _ in run_intervals:
            run = db.session.get(RunModel, run_id)
            run_data_cache[run_id] = read_series(run).as_tuple() if run else ([], [], [])

        user_songs = (
            db.session.query(UserSongHistoryModel)
            .filter_by(user_id=user_id)
            .filter(UserSongHistoryModel.run_id.isnot(None))
            .all()
        )

        analyses_to_add = []
        for user_song in user_songs:
            timestamps, hr, pace_s_per_km = run_data_cache.get(user_song.run_id, ([], [], []))
            seg = {
                "start_time": user_song.played_at,
                "end_time": user_song.played_at + dt.timedelta(seconds=user_song.time_played),
            }
            score = score_segment(seg, timestamps, pace_s_per_km, hr)

            if score is None or (isinstance(score, float) and (score != score)):  # skip invalid
                continue
            exists = (
                db.session.query(RunSongAnalysisModel.id)
                .filter_by(run_id=user_song.run_id, user_song_id=user_song.id)
                .first()
            )
            if exists:
                continue

            analyses_to_add.append(
                RunSongAnalysisModel(
                    run_id=user_song.run_id,
                    user_song_id=user_song.id,
                    performance_score=score,
                    user_id=user_id,
                )
            )

            if len(analyses_to_add) >= batch_size:
                db.session.add_all(analyses_to_add)
                db.session.commit()
                analyses_to_add.clear()

        if analyses_to_add:
            db.session.add_all(analyses_to_add)
            db.session.commit()

    except Exception as e:
        db.session.rollback()
        stats["errors"] += 1
        stats["note"] = f"Error during score calculation: {e}"

    return stats  # stats
