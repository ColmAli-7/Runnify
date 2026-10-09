"""The runs list and each run's results sheet."""

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import exists

from runnify.models import Run, UserSongHistory
from runnify.services import charts
from runnify.services.results import run_results, run_summaries

bp = Blueprint("runs", __name__)

PER_PAGE = 25


@bp.route("/runs")
@login_required
def index():
    """The runner's runs, newest first; ``?music=1`` keeps only runs with matched songs."""
    music_only = request.args.get("music") == "1"
    query = Run.query.filter_by(user_id=current_user.id)
    if music_only:
        query = query.filter(
            exists().where(UserSongHistory.run_id == Run.id, UserSongHistory.user_id == Run.user_id)
        )
    pagination = query.order_by(Run.date_time.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=PER_PAGE, error_out=False
    )
    return render_template(
        "runs/index.html",
        pagination=pagination,
        summaries=run_summaries([run.id for run in pagination.items]),
        music_only=music_only,
    )


@bp.route("/runs/<int:run_id>")
@login_required
def detail(run_id):
    """One run's results: pace and heart rate through the run, and every song ranked."""
    run = Run.query.filter_by(id=run_id, user_id=current_user.id).first_or_404()
    results = run_results(run)
    bands = results.bands()
    mine = Run.query.filter_by(user_id=current_user.id)
    older = mine.filter(Run.date_time < run.date_time).order_by(Run.date_time.desc()).first()
    newer = mine.filter(Run.date_time > run.date_time).order_by(Run.date_time.asc()).first()
    pace_chart = charts.run_chart(results.series.paces, bands)
    heart_chart = charts.heart_chart(results.series.heart_rates, bands)
    return render_template(
        "runs/detail.html",
        run=run,
        results=results,
        pace_chart=pace_chart,
        heart_chart=heart_chart,
        older=older,
        newer=newer,
        timeline={
            "seconds": pace_chart.seconds,
            "pace": pace_chart.points,
            "heart": heart_chart.points,
            "songs": [[start, end, label] for start, end, label, _kind in bands],
        },
    )
