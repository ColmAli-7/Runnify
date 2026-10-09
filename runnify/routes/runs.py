"""Activity list and the per-run analysis page."""

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import and_, exists

from runnify.models import Run, UserSongHistory
from runnify.services.scoring import score_segment
from runnify.services.segments import load_song_segments
from runnify.services.streams import load_series

bp = Blueprint("activities", __name__)  # blueprint for activity routes


@bp.route("/activities")
@login_required
def activities():
    """List the user's runs, newest first; ``?music_only=true`` keeps only runs with matched songs."""
    music_only = request.args.get("music_only", "false") == "true"  # toggle for music-linked runs
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


@bp.route("/activity/<int:run_id>")
@login_required
def activity_detail(run_id):
    """Render the analysis page for one run.

    Parses the run's FIT file, finds the songs played during it, scores each
    one and passes a JSON-ready payload (run summary, pace/HR timeline and
    song segments) to the template for charting.
    """
    run = Run.query.filter_by(id=run_id, user_id=current_user.id).first()
    if not run:
        abort(404, description="Run not found")  # invalid id or unauthorised access
    ts, hr, pace = load_series(run).as_tuple()  # second-by-second samples
    if not ts:
        abort(400, description="No second-by-second data was recorded for this run")

    run_start, run_end = ts[0], ts[-1]
    segments = load_song_segments(run.user_id, run_start, run_end)  # get songs played during run

    for seg in segments:
        seg["score"] = score_segment(seg, ts, pace, hr)  # compute score per song

    # payload for frontend rendering of activity analysis
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
            "t_s": [int((t - run_start).total_seconds()) for t in ts],  # time in seconds from start
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
