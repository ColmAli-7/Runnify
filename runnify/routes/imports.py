"""Importing Spotify extended streaming history: the guide and the upload."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from runnify.extensions import limiter
from runnify.models import Run
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services import imports
from runnify.services.history_import import HistoryArchiveError

bp = Blueprint("imports", __name__)


@bp.route("/import", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("UPLOAD"), methods=["POST"], key_func=user_or_ip)
def index():
    """Show how to get the Spotify export and the upload form; on POST, import it in the background."""
    has_runs = Run.query.filter_by(user_id=current_user.id).first() is not None
    if request.method == "GET":
        return render_template("spotify_upload_history.html", has_runs=has_runs)

    file = request.files.get("history_zip")
    if not file or not file.filename or not file.filename.lower().endswith(".zip"):
        flash("Choose the .zip file Spotify sent you.", "error")
        return redirect(url_for("imports.index"))
    if not has_runs:
        flash("Sync your runs from Garmin first; songs are matched to runs.", "info")
        return redirect(url_for("imports.index"))
    if current_user.history_import_state == "importing":
        flash("An import is already running. It will finish shortly.", "info")
        return redirect(url_for("imports.index"))

    path = imports.save_upload(file)
    try:
        imports.check_upload(path)
    except HistoryArchiveError as error:
        imports.discard(path)
        flash(str(error), "error")
        return redirect(url_for("imports.index"))
    imports.start_background_import(current_app._get_current_object(), current_user.id, path)
    flash(
        "Importing your listening history. Matched songs appear as soon as it finishes.", "success"
    )
    return redirect(url_for("imports.index"))
