"""Music Insights: aggregate song performance statistics over a date range."""

from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory, utcnow

bp = Blueprint("music_insights", __name__)  # blueprint for music insights


def _date_bounds(label: str):
    """Map a range label (e.g. ``"Last 30 days"``) to ``(start, end)``; ``(None, None)`` means all time."""
    now = utcnow()
    if label == "Last 7 days":
        return now - timedelta(days=7), now
    elif label == "Last 30 days":
        return now - timedelta(days=30), now
    elif label == "Last 90 days":
        return now - timedelta(days=90), now
    elif label == "Year to date":
        return datetime(now.year, 1, 1), now
    else:
        return None, None  # all time


@bp.route("/music-insights")
@login_required
def music_insights_page():
    """Render Music Insights for the ``?range=`` window (default ``Last 30 days``).

    Includes average score, best and most-played songs, distinct song count,
    monthly score trend, plays-vs-score data and two top-10 tables.
    """
    range_label = request.args.get("range", "Last 30 days")
    start, end = _date_bounds(range_label)  # determine time range

    base_filter = [RunSongAnalysis.user_id == current_user.id]
    if start:
        base_filter += [Run.date_time >= start, Run.date_time <= end]

    avg_score = (
        db.session.query(func.avg(RunSongAnalysis.performance_score))
        .join(Run, Run.id == RunSongAnalysis.run_id)
        .filter(*base_filter)
        .scalar()
    )  # average performance score in range

    best_song = (
        db.session.query(Song.name, func.avg(RunSongAnalysis.performance_score))
        .join(UserSongHistory, Song.id == UserSongHistory.song_id)
        .join(RunSongAnalysis, RunSongAnalysis.user_song_id == UserSongHistory.id)
        .join(Run, Run.id == RunSongAnalysis.run_id)
        .filter(*base_filter)
        .group_by(Song.name)
        .order_by(func.avg(RunSongAnalysis.performance_score).desc())
        .first()
    )
    best_song = best_song[0] if best_song else None  # highest scoring song

    most_played = (
        db.session.query(Song.name, func.count(UserSongHistory.id))
        .join(UserSongHistory, Song.id == UserSongHistory.song_id)
        .join(Run, Run.id == UserSongHistory.run_id)
        .filter(UserSongHistory.user_id == current_user.id)
    )
    if start:
        most_played = most_played.filter(Run.date_time >= start, Run.date_time <= end)
    most_played = (
        most_played.group_by(Song.name).order_by(func.count(UserSongHistory.id).desc()).first()
    )
    most_played = most_played[0] if most_played else None  # most frequently played

    total_songs = db.session.query(func.count(func.distinct(UserSongHistory.song_id))).filter(
        UserSongHistory.user_id == current_user.id
    )
    if start:
        total_songs = total_songs.join(Run, Run.id == UserSongHistory.run_id).filter(
            Run.date_time >= start, Run.date_time <= end
        )
    total_songs = total_songs.scalar() or 0  # total distinct songs

    # score progression over time, grouped by month in python so it works on any database
    monthly_scores = defaultdict(list)
    for run_date, score in (
        db.session.query(Run.date_time, RunSongAnalysis.performance_score)
        .join(Run, Run.id == RunSongAnalysis.run_id)
        .filter(*base_filter)
    ):
        if run_date is not None and score is not None:
            monthly_scores[run_date.strftime("%Y-%m")].append(score)
    performance_trend = [
        {"month": month, "avg_score": sum(scores) / len(scores)}
        for month, scores in sorted(monthly_scores.items())
    ]

    play_perf = (
        db.session.query(
            Song.name,
            func.count(UserSongHistory.id).label("plays"),
            func.avg(RunSongAnalysis.performance_score).label("score"),
        )
        .join(UserSongHistory, Song.id == UserSongHistory.song_id)
        .outerjoin(RunSongAnalysis, RunSongAnalysis.user_song_id == UserSongHistory.id)
        .join(Run, Run.id == UserSongHistory.run_id)
        .filter(UserSongHistory.user_id == current_user.id)
    )
    if start:
        play_perf = play_perf.filter(Run.date_time >= start, Run.date_time <= end)
    play_perf = play_perf.group_by(Song.name).all()  # plays and avg score per song

    top_performing = (
        db.session.query(Song.name, func.avg(RunSongAnalysis.performance_score))
        .join(UserSongHistory, Song.id == UserSongHistory.song_id)
        .join(RunSongAnalysis, RunSongAnalysis.user_song_id == UserSongHistory.id)
        .join(Run, Run.id == RunSongAnalysis.run_id)
        .filter(*base_filter)
        .group_by(Song.name)
        .order_by(func.avg(RunSongAnalysis.performance_score).desc())
        .limit(10)
        .all()
    )  # top 10 songs by performance

    most_listened = (
        db.session.query(
            Song.name,
            func.count(UserSongHistory.id).label("plays"),
            func.avg(RunSongAnalysis.performance_score).label("score"),
        )
        .join(UserSongHistory, Song.id == UserSongHistory.song_id)
        .outerjoin(RunSongAnalysis, RunSongAnalysis.user_song_id == UserSongHistory.id)
        .join(Run, Run.id == UserSongHistory.run_id)
        .filter(UserSongHistory.user_id == current_user.id)
    )
    if start:
        most_listened = most_listened.filter(Run.date_time >= start, Run.date_time <= end)
    most_listened = (
        most_listened.group_by(Song.name)
        .order_by(func.count(UserSongHistory.id).desc())
        .limit(10)
        .all()
    )  # top 10 most played songs
    print(most_listened)
    return render_template(
        "music_insights.html",
        avg_score=round(avg_score, 2) if avg_score is not None else None,
        best_song=best_song,
        most_played=most_played,
        total_songs=total_songs,
        performance_trend=performance_trend,
        play_perf=play_perf,
        top_performing=top_performing,
        most_listened=most_listened,
    )
