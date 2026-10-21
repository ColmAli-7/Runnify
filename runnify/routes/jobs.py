"""The signed-in runner's background jobs: on every page, and as JSON for scripts.

See :mod:`runnify.services.jobs`. ``js/jobs.js`` polls :func:`status` while a
job runs, so its progress moves on without reloading the page.
"""

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from runnify.services.jobs import jobs_of

bp = Blueprint("jobs", __name__)


@bp.app_context_processor
def background_jobs():
    """``jobs.garmin`` and ``jobs.history`` for templates, when someone is signed in."""
    return {"jobs": jobs_of(current_user) if current_user.is_authenticated else {}}


@bp.route("/jobs")
@login_required
def status():
    """What the runner's Garmin sync and history import are doing, as JSON."""
    response = jsonify({kind: job.as_dict() for kind, job in jobs_of(current_user).items()})
    response.headers["Cache-Control"] = "no-store"
    return response
