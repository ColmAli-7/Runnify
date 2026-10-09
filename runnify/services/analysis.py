"""Computing and storing each song's effect on each run.

:func:`rescore_run` is idempotent: it replaces a run's stored effects with
freshly computed ones, so it serves the history import, re-scoring after the
method improves (``flask --app runnify scores rebuild``) and new streams alike.
"""

from datetime import timedelta

from sqlalchemy import delete

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory
from runnify.services.scoring import METHOD_VERSION, song_effect
from runnify.services.streams import load_series


def song_segments(run, series):
    """The run's song plays as ``(play, song, start, end)``, trimmed to the recorded samples."""
    if not len(series):
        return []
    first, last = series.timestamps[0], series.timestamps[-1]
    rows = (
        db.session.query(UserSongHistory, Song)
        .join(Song, Song.id == UserSongHistory.song_id)
        .filter(UserSongHistory.run_id == run.id)
        .order_by(UserSongHistory.played_at)
        .all()
    )
    segments = []
    for play, song in rows:
        start = max(play.played_at, first)
        end = min(play.played_at + timedelta(seconds=play.time_played or 0), last)
        if end > start:
            segments.append((play, song, start, end))
    return segments


def rescore_run(run, series=None):
    """Recompute and store the effect of every song played during ``run``.

    Returns:
        How many song plays received a score.
    """
    series = series if series is not None else load_series(run)
    db.session.execute(delete(RunSongAnalysis).where(RunSongAnalysis.run_id == run.id))
    scored = 0
    for play, _song, start, end in song_segments(run, series):
        effect = song_effect(series, start, end)
        if effect.score is None:
            continue
        db.session.add(
            RunSongAnalysis(
                run_id=run.id,
                user_song_id=play.id,
                user_id=run.user_id,
                performance_score=effect.score,
                pace_delta=effect.pace_delta,
                hr_delta=effect.hr_delta,
                seconds=effect.seconds,
                position=effect.position,
                method_version=METHOD_VERSION,
            )
        )
        scored += 1
    return scored


def rescore_runs(run_ids):
    """Rescore several runs; returns the total number of scored song plays."""
    total = 0
    for run in Run.query.filter(Run.id.in_(list(run_ids))).all():
        total += rescore_run(run)
    return total
