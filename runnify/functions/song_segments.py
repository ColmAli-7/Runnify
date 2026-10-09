"""Load the songs that were playing during a run."""

from datetime import timedelta
from sqlalchemy import and_
from models import db, UserSongHistory, Song


def _end_time(played_at, time_played):
    """Return when a play ended, treating ``time_played`` >= 10000 as milliseconds."""
    if time_played is None:
        return played_at
    if time_played >= 10000:  # handles values in ms
        return played_at + timedelta(milliseconds=int(time_played))
    return played_at + timedelta(seconds=int(time_played))  # values in s


def load_song_segments(user_id, run_start, run_end):
    """Return the song segments that overlap a run, trimmed to the run window.

    Args:
        user_id: Owner of the song history.
        run_start: Run start time (naive UTC ``datetime``).
        run_end: Run end time (naive UTC ``datetime``).

    Returns:
        A list of dicts with ``track_name``, ``artist_name``, ``start_time``
        and ``end_time``, ordered by play time, with duplicate plays removed.
    """
    query = (
        db.session.query(UserSongHistory, Song)
        .join(Song, Song.id == UserSongHistory.song_id)
        .filter(UserSongHistory.user_id == user_id)
        .filter(UserSongHistory.played_at < run_end)
        .filter(UserSongHistory.played_at > run_start - timedelta(hours=6))
        .order_by(UserSongHistory.played_at.asc())
    )
    results = query.all()

    song_segments = []
    processed_keys = set()  # avoid duplicates

    for song_history, song in results:
        key = (song_history.song_id, song_history.played_at)
        if key in processed_keys:  # skip repeated song instances
            continue
        processed_keys.add(key)

        play_start = song_history.played_at
        play_end = _end_time(play_start, song_history.time_played)

        if play_end <= run_start or play_start >= run_end:  # no overlap
            continue

        segment_start = max(run_start, play_start)  # trim segment to run window
        segment_end = min(run_end, play_end)
        if segment_end <= segment_start:
            continue

        song_segments.append(
            {
                "track_name": song.name or "",
                "artist_name": song.artist or "",
                "start_time": segment_start,
                "end_time": segment_end,
            }
        )

    return song_segments
