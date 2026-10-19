"""The runs list, each run's results, and changing a run's laps and kind."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import exists

from runnify.extensions import db
from runnify.filters import plural
from runnify.forms import LapsForm, first_error
from runnify.models import Run, UserSongHistory
from runnify.services import charts, workouts
from runnify.services import laps as lap_service
from runnify.services.analysis import rescore_run
from runnify.services.laps import KINDS, RUN_TYPES
from runnify.services.results import run_results, run_summaries
from runnify.services.streams import load_series

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
        run_types=RUN_TYPES,
    )


@bp.route("/runs/<int:run_id>")
@login_required
def detail(run_id):
    """One run's results: pace and heart rate through the run, its laps, and every song ranked."""
    run = Run.query.filter_by(id=run_id, user_id=current_user.id).first_or_404()
    results = run_results(run)
    bands = results.bands()
    mine = Run.query.filter_by(user_id=current_user.id)
    older = mine.filter(Run.date_time < run.date_time).order_by(Run.date_time.desc()).first()
    newer = mine.filter(Run.date_time > run.date_time).order_by(Run.date_time.asc()).first()
    pace_chart = charts.run_chart(results.series.paces, bands)
    heart_chart = charts.heart_chart(results.series.heart_rates, bands)
    laps = run.laps
    lap_blocks = (
        charts.lap_lane(
            [(lap.start_second, lap.end_second, lap.kind, KINDS[lap.kind]) for lap in laps],
            pace_chart.seconds,
        )
        if len(laps) > 1
        else []
    )
    return render_template(
        "runs/detail.html",
        run=run,
        results=results,
        pace_chart=pace_chart,
        heart_chart=heart_chart,
        laps=laps,
        lap_blocks=lap_blocks,
        lap_kinds=KINDS,
        run_types=RUN_TYPES,
        older=older,
        newer=newer,
        timeline={
            "seconds": pace_chart.seconds,
            "pace": pace_chart.points,
            "heart": heart_chart.points,
            "pace_range": [pace_chart.top, pace_chart.bottom],
            "heart_range": [heart_chart.top, heart_chart.bottom],
            "songs": [
                [
                    row.start,
                    row.start + row.seconds,
                    row.song.name or "Unknown track",
                    row.song.artist or "",
                    None if row.lift is None else round(row.lift, 1),
                ]
                for row in results.rows
            ],
        },
    )


def _change(run, series, action, form):
    """Make the change the button ``action`` asks for; returns what to tell the runner."""
    if action == "type":
        lap_service.set_run_type(run, form.run_type.data)
        if run.run_type_manual:
            return f"Saved as {RUN_TYPES[run.run_type].lower()}."
        return "Runnify will work out the kind of run again."
    if action == "kinds":
        lap_service.set_kinds(run, series, request.form.getlist("kind"))
        return "Laps saved, and the songs measured again against them."
    if action.startswith("merge-") and action.removeprefix("merge-").isdigit():
        position = int(action.removeprefix("merge-"))
        lap_service.set_kinds(run, series, request.form.getlist("kind"))
        lap_service.merge_laps(run, series, position)
        return f"Laps {position + 1} and {position + 2} joined."
    if action == "split":
        second = lap_service.parse_time(form.split_at.data)
        if second is None:
            raise lap_service.LapError("Give the time as minutes and seconds, like 12:30.")
        position = lap_service.split_lap(run, series, second)
        return f"Lap {position + 1} split at {form.split_at.data}."
    if action == "reset":
        lap_service.reset_laps(run)
        return "Laps worked out again from the run."
    if action == "workout":
        laps = workouts.apply_workout(run, series, form.workout.data)
        return f"Your workout is lined up with the run: {plural(len(laps), 'lap')}."
    raise lap_service.LapError("That change isn't one Runnify knows how to make.")


@bp.route("/runs/<int:run_id>/laps", methods=["GET", "POST"])
@login_required
def laps(run_id):
    """Change a run's kind or its laps, then measure its songs again.

    Each small form on the run page posts here with the button it was sent by.
    A GET returns to the run, so a form that expired lands back on the run page.
    """
    run = Run.query.filter_by(id=run_id, user_id=current_user.id).first_or_404()
    back = redirect(url_for("runs.detail", run_id=run.id, _anchor="laps"))
    if request.method == "GET":
        return back
    form = LapsForm()
    if not form.validate_on_submit():
        flash(first_error(form) or "That change couldn't be made.", "error")
        return back
    series = load_series(run)
    if not len(series):
        flash("This run has no second-by-second recording, so it has no laps to change.", "error")
        return back
    try:
        message = _change(run, series, request.form.get("action", ""), form)
    except lap_service.LapError as error:
        db.session.rollback()
        flash(str(error), "error")
        return back
    rescore_run(run, series)
    db.session.commit()
    flash(message, "success")
    return back
