"""Builders for realistic test data: a run with a recorded stream and scored songs."""

from datetime import datetime, timedelta

from runnify.extensions import db
from runnify.models import Run, Song, UserSongHistory
from runnify.services.analysis import rescore_run
from runnify.services.fit import Series
from runnify.services.streams import save_stream

START = datetime(2026, 10, 5, 7, 0)
LENGTH = 20 * 60  # seconds

# id, name, start second, seconds played, pace while playing (s/km), skipped
PLAYS = [
    ("steady", "Steady Song", 60, 180, None, False),
    ("fast", "Fast Song", 480, 180, 280.0, False),
    ("slow", "Slow Song", 840, 180, 320.0, False),
    ("skipped", "Skipped Song", 1080, 10, None, True),
]


def make_scored_run(user_id, start=START, activity_id="scored-run"):
    """A 20-minute run at 5:00/km, faster during "Fast Song" and slower during "Slow Song"."""
    paces = [300.0] * LENGTH
    for _id, _name, at, seconds, pace, _skipped in PLAYS:
        if pace is not None:
            paces[at : at + seconds] = [pace] * seconds
    series = Series(
        timestamps=[start + timedelta(seconds=s) for s in range(LENGTH)],
        heart_rates=[150] * LENGTH,
        paces=paces,
    )
    run = Run(
        user_id=user_id,
        activity_id=activity_id,
        date_time=start,
        distance=4000.0,
        duration=LENGTH,
        avg_hr=150,
    )
    db.session.add(run)
    db.session.flush()
    save_stream(run, series)
    for song_id, name, at, seconds, _pace, skipped in PLAYS:
        if db.session.get(Song, song_id) is None:
            db.session.add(Song(id=song_id, name=name, artist="Test Artist", duration=200))
        db.session.add(
            UserSongHistory(
                user_id=user_id,
                song_id=song_id,
                run_id=run.id,
                played_at=start + timedelta(seconds=at),
                time_played=seconds,
                skipped=skipped,
            )
        )
    db.session.flush()
    rescore_run(run, series)
    db.session.commit()
    return run.id
