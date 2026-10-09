"""The dashboard: setup progress, the latest run's results, recent weeks and standout songs."""

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from runnify.filters import short_day
from runnify.models import Run
from runnify.services import charts, insights
from runnify.services import dashboard as dashboard_service
from runnify.services.results import run_results

bp = Blueprint("dashboard", __name__)

WEEKS = 12


@bp.route("/dashboard")
@login_required
def index():
    """Show where the runner is in setup and how their running and music are going."""
    user = current_user
    setup = dashboard_service.setup_state(user)
    latest = Run.query.filter_by(user_id=user.id).order_by(Run.date_time.desc()).first()
    results = run_results(latest) if latest else None

    weeks = dashboard_service.weekly_distance(user.id, weeks=WEEKS)
    week_chart = charts.bar_chart(
        [(short_day(start), metres / 1000) for start, metres in weeks],
        value_format=lambda km: f"{km:.0f}" if km >= 0.5 else "",
    )
    effects = insights.song_effects(user.id, since=insights.range_start("90d"))
    return render_template(
        "dashboard/index.html",
        setup=setup,
        latest=latest,
        results=results,
        latest_chart=charts.run_chart(results.series.paces, results.bands()) if results else None,
        weeks=weeks,
        week_chart=week_chart,
        period=dashboard_service.totals(user.id, since=weeks[0][0]),
        all_time=dashboard_service.totals(user.id),
        power=insights.ranked(effects, best=True, limit=3),
        drag=insights.ranked(effects, best=False, limit=3),
    )
