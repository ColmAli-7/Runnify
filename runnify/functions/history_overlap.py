import io, zipfile, datetime as dt
from typing import Dict, Any
import ijson
from sqlalchemy import and_, exists


def _parse_ts_stop_utc(ts_str: str):
    # converts spotify timestamp string to utc datetime
    if not ts_str:
        return None
    try:
        return dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            if ts_str.endswith("Z"):
                d = dt.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                return d.astimezone(dt.timezone.utc).replace(tzinfo=None)
            d = dt.datetime.fromisoformat(ts_str)
            return d.astimezone(dt.timezone.utc).replace(tzinfo=None)
        except Exception:
            return None


def _row_interval(row: Dict[str, Any]):
    # gets start and end times for a single song play from spotify data
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


def _is_podcast_or_video(row: Dict[str, Any]):
    # filters out podcast and video plays
    return bool(
        row.get("episode_name")
        or row.get("episode_show_name")
        or row.get("spotify_episode_uri")
    )


def _spotify_track_id(row: Dict[str, Any]):
    # extracts spotify track id from uri
    uri = row.get("spotify_track_uri")
    if not uri:
        return None
    parts = uri.split(":")
    if len(parts) >= 3 and parts[1] == "track":
        return parts[2]
    return None


def _names(row: Dict[str, Any]):
    # extracts track, artist and album names
    return (
        row.get("master_metadata_track_name"),
        row.get("master_metadata_album_artist_name"),
        row.get("master_metadata_album_album_name"),
    )


def _overlap(
    a_start: dt.datetime, a_end: dt.datetime, b_start: dt.datetime, b_end: dt.datetime
):
    # returns overlapping time range between two intervals
    s = max(a_start, b_start)
    e = min(a_end, b_end)
    return (s, e) if s < e else None


def _seconds(td: dt.timedelta):
    return max(0, int(td.total_seconds()))  # ensures no negative values


def _collect_run_intervals(db, RunModel, user_id: int):
    # fetches all runs and converts to time intervals
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
    # iterates through large json files efficiently
    try:
        for row in ijson.items(file_like, "item"):
            if isinstance(row, dict):
                yield row
    except ijson.JSONError:
        return


def import_history_zip_overlapping_runs(
    *,
    zip_bytes: bytes,
    user_id: int,
    db,
    RunModel,
    SongModel,
    UserSongHistoryModel,
    RunSongAnalysisModel,
    read_fit_to_series,
    _score_segment,
    batch_size: int = 500,
    min_overlap_seconds: int = 1,
):
    # imports extended spotify history zip and links plays to runs
    stats = dict(files=0, json_files=0, rows=0, saved=0, skipped=0, errors=0, note=None)
    run_intervals = _collect_run_intervals(db, RunModel, user_id)
    if not run_intervals:
        return {**stats, "note": "User has no runs"}

    run_data_cache = {}  # store fit data to avoid rereading
    user_songs_to_add = []
    seen_songs = set()

    # process all spotify json files in the uploaded zip
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
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
                            track, artist, album = _names(row)
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
            if run and getattr(run, "fit_file_path", None):
                timestamps, pace_s_per_km, hr = read_fit_to_series(run.fit_file_path)
                run_data_cache[run_id] = (timestamps, pace_s_per_km, hr)
            else:
                run_data_cache[run_id] = ([], [], [])

        user_songs = (
            db.session.query(UserSongHistoryModel)
            .filter_by(user_id=user_id)
            .filter(UserSongHistoryModel.run_id.isnot(None))
            .all()
        )

        analyses_to_add = []
        for user_song in user_songs:
            timestamps, hr, pace_s_per_km = run_data_cache.get(
                user_song.run_id, ([], [], [])
            )
            seg = {
                "start_time": user_song.played_at,
                "end_time": user_song.played_at
                + dt.timedelta(seconds=user_song.time_played),
            }
            score = _score_segment(seg, timestamps, pace_s_per_km, hr)

            if score is None or (
                isinstance(score, float) and (score != score)
            ):  # skip invalid
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
