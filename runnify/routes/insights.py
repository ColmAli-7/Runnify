"""Insights: what the runner's songs did across many runs (see :mod:`runnify.services.insights`)."""

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from runnify.services import insights

bp = Blueprint("insights", __name__)


@bp.route("/insights")
@login_required
def index():
    """Every finding for the ``?range=`` window (30d, 90d, year or all; 90 days by default)."""
    overview = insights.overview(current_user.id, request.args.get("range", insights.DEFAULT_RANGE))
    strengths = [phase.strength for phase in overview.phases if phase.strength is not None]
    return render_template(
        "insights/index.html",
        overview=overview,
        ranges=insights.RANGES,
        strongest=max(strengths, default=None),
        min_phase_plays=insights.MIN_PHASE_PLAYS,
    )
