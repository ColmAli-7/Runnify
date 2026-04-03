from flask import Blueprint, render_template, abort, request
from flask_login import current_user, login_required
from statistics import mean, pstdev
from models import db, Run, RunSongAnalysis, UserSongHistory
from functions.fit_util import read_fit_to_series
from sqlalchemy import exists, and_
from functions.song_segments import load_song_segments

get_activities = Blueprint("activities", __name__)  # blueprint for activity routes


@get_activities.route("/activities")
@login_required
def activities():
    music_only = (
        request.args.get("music_only", "false") == "true"
    )  # toggle for music-linked runs
    query = Run.query.filter_by(user_id=current_user.id)
    if music_only:
        query = query.filter(
            exists().where(
                and_(
                    UserSongHistory.user_id == Run.user_id,
                    UserSongHistory.run_id == Run.id,
                )
            )
        )
    runs = query.order_by(Run.date_time.desc()).all()  # most recent first
    return render_template("activities.html", runs=runs, music_only=music_only)


def _score_segment(seg, timestamps, pace_s_per_km, hr=None):
    song_paces = [
        pace
        for t, pace in zip(timestamps, pace_s_per_km)
        if pace is not None and seg["start_time"] <= t <= seg["end_time"]
    ]  # paces during song segment
    run_paces = [pace for pace in pace_s_per_km if pace is not None]  # all valid paces
    if len(song_paces) < 5 or len(run_paces) < 10:
        return None  # skip if not enough data
    run_avg_pace = mean(run_paces)
    run_std_pace = pstdev(run_paces) if len(run_paces) > 1 else 0
    song_avg_pace = mean(song_paces)
    if run_std_pace == 0:
        z_score = 0
    else:
        z_score = (run_avg_pace - song_avg_pace) / run_std_pace  # compare to mean pace
    score = 50 + 20 * z_score  # scale to 0–100 range
    return round(max(0, min(100, score)), 1)


@login_required
@get_activities.route("/activity/<int:run_id>")
def activity_detail(run_id):
    run = Run.query.filter_by(id=run_id, user_id=current_user.id).first()
    if not run:
        abort(404, description="Run not found")  # invalid id or unauthorised access
    if not run.fit_file_path:
        abort(
            400, description="No FIT file recorded for this run"
        )  # no fit file present

    ts, hr, pace = read_fit_to_series(run.fit_file_path)  # parse FIT file
    if not ts:
        abort(400, description="No records found in FIT")  # empty FIT file

    run_start, run_end = ts[0], ts[-1]
    segments = load_song_segments(
        run.user_id, run_start, run_end
    )  # get songs played during run

    for seg in segments:
        seg["score"] = _score_segment(seg, ts, pace, hr)  # compute score per song

    #payload for frontend rendering of activity analysis
    payload = {
        "run": {
            "id": run.id,
            "activity_id": run.activity_id,
            "start_utc": run_start.isoformat(),
            "duration_s": int((run_end - run_start).total_seconds()),
            "distance_m": (
                (run.distance or 0) * 1000
                if (run.distance and run.distance < 1000)
                else (run.distance or 0)
            ),
            "avg_hr": run.avg_hr,
        },
        "timeline": {
            "t_s": [
                int((t - run_start).total_seconds()) for t in ts
            ],  # time in seconds from start
            "pace_s_per_km": [round(v, 1) if v is not None else None for v in pace],
            "hr_bpm": hr,
        },
        "segments": [
            {
                "track_name": s["track_name"],
                "artist_name": s["artist_name"],
                "start_s": int(
                    (s["start_time"] - run_start).total_seconds()
                ),  # segment start relative to run
                "end_s": int(
                    (s["end_time"] - run_start).total_seconds()
                ),  # segment end relative to run
                "score": s["score"],
            }
            for s in segments
        ],
    }

    return render_template("activity_analysis.html", payload=payload)
