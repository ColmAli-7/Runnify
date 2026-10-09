"""User dashboard: headline stats and monthly mileage."""

from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from runnify.extensions import db
from runnify.models import Run, Song, UserSongHistory
from collections import defaultdict
import datetime as dt

bp = Blueprint("dash", __name__)  # dashboard blueprint


@bp.route("/dashboard")
@login_required
def dashboard():
    """Render the dashboard.

    Shows total runs, songs and distance, favourite artist, last run,
    fastest-paced run (with the first song played), longest run and a
    monthly mileage chart.
    """
    user = current_user
    total_runs = Run.query.filter_by(user_id=user.id).count()  # total run count
    total_songs = UserSongHistory.query.filter_by(
        user_id=user.id
    ).count()  # total songs played
    total_distance = (
        db.session.query(func.sum(Run.distance)).filter(Run.user_id == user.id).scalar()
    )
    total_distance = total_distance if total_distance else 0  # handle null distance

    favourite_artist = (
        db.session.query(Song.artist, func.count(UserSongHistory.id))
        .join(UserSongHistory, Song.id == UserSongHistory.song_id)
        .filter(UserSongHistory.user_id == user.id)
        .group_by(Song.artist)
        .order_by(func.count(UserSongHistory.id).desc())
        .first()
    )
    favourite_artist = (
        favourite_artist[0] if favourite_artist else "—"
    )  # most played artist

    last_run = (
        Run.query.filter_by(user_id=user.id).order_by(Run.date_time.desc()).first()
    )

    last_run_display = "—"
    if last_run:
        pace_s = (
            last_run.duration / (last_run.distance / 1000)
            if last_run.distance
            else None
        )  # sec per km
        if pace_s:
            pace_str = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"
        else:
            pace_str = "—"
        last_run_display = f"{(last_run.distance/1000):.1f} km | {pace_str} | Avg HR: {last_run.avg_hr or '—'}"  # format last run summary

    fastest_km_display = "—"
    fastest_km_date = None

    fastest_km_run = (
        Run.query.filter(Run.user_id == user.id, Run.distance >= 1000)
        .order_by((Run.duration / (Run.distance / 1000)).asc())  # lowest pace first
        .first()
    )
    if fastest_km_run:
        pace_s = fastest_km_run.duration / (fastest_km_run.distance / 1000)
        pace_str = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}"
        song = (
            db.session.query(Song.name, Song.artist)
            .join(UserSongHistory, Song.id == UserSongHistory.song_id)
            .filter(UserSongHistory.run_id == fastest_km_run.id)
            .order_by(UserSongHistory.played_at.asc())
            .first()
        )
        if song:
            fastest_km_display = (
                f"{pace_str} — {song[1]} - {song[0]}"  # show artist and song
            )
        else:
            fastest_km_display = pace_str
        fastest_km_date = fastest_km_run.date_time.strftime("%d %b %Y")  # format date

    longest_run_display = "—"
    longest_run_date = None

    longest_run = (
        Run.query.filter(Run.user_id == user.id)
        .order_by(Run.distance.desc())  # highest distance first
        .first()
    )

    if longest_run:
        dist_km = longest_run.distance / 1000 if longest_run.distance else 0
        pace_s = (
            longest_run.duration / (longest_run.distance / 1000)
            if longest_run.distance
            else None
        )
        if pace_s:
            pace_str = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"
        else:
            pace_str = "—"
        longest_run_display = (
            f"{dist_km:.1f} km | {pace_str} | Avg HR: {longest_run.avg_hr or '—'}"
        )
        longest_run_date = longest_run.date_time.strftime("%d %b %Y")

    monthly_mileage = defaultdict(float)
    runs = Run.query.filter_by(user_id=user.id).all()
    for run in runs:
        month_key = run.date_time.strftime("%Y-%m")  # month grouping key
        monthly_mileage[month_key] += run.distance / 1000  # convert to km
    monthly_mileage = dict(sorted(monthly_mileage.items()))  # sort chronologically

    # render all stats to dashboard
    return render_template(
        "dashboard.html",
        monthly_labels=list(monthly_mileage.keys()),
        monthly_values=list(monthly_mileage.values()),
        total_runs=total_runs,
        total_songs=total_songs,
        total_distance=total_distance,
        favourite_artist=favourite_artist,
        last_run_display=last_run_display,
        fastest_km_display=fastest_km_display,
        fastest_km_date=fastest_km_date,
        longest_run_display=longest_run_display,
        longest_run_date=longest_run_date,
    )
