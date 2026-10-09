"""Spotify integration (mounted under ``/spotify``).

Handles the Spotify OAuth flow and the upload of a user's extended streaming
history zip. OAuth details live in :mod:`runnify.services.spotify`.
"""

import hmac
import logging
import secrets

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from runnify.extensions import db, limiter
from runnify.models import Run
from runnify.security import audit
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services import imports
from runnify.services import spotify as spotify_service
from runnify.services.history_import import HistoryArchiveError

bp = Blueprint("spotify", __name__)  # spotify integration routes
logger = logging.getLogger(__name__)

STATE_KEY = "spotify_oauth_state"


@bp.route("/login")
@login_required
def login_spotify():
    """Send the user to Spotify's consent page with a one-time anti-CSRF ``state``."""
    state = secrets.token_urlsafe(24)
    session[STATE_KEY] = state
    return redirect(spotify_service.authorize_url(state))


@bp.route("/callback")
@login_required
def callback():
    """OAuth redirect target: check ``state``, exchange the code and store the tokens.

    The ``state`` check stops another site completing this flow with its own
    code, which would attach someone else's Spotify account to this user.
    """
    expected = session.pop(STATE_KEY, None)
    returned = request.args.get("state", "")
    if not expected or not hmac.compare_digest(expected, returned):
        flash("That Spotify connection request wasn't started here, so it was ignored.", "error")
        return redirect(url_for("dash.dashboard"))
    if request.args.get("error"):
        flash("Spotify wasn't connected.", "info")
        return redirect(url_for("dash.dashboard"))
    code = request.args.get("code")
    if not code:
        abort(400)
    try:
        token_info = spotify_service.exchange_code(code)
    except Exception:
        logger.exception("Spotify token exchange failed")
        flash("Spotify couldn't be connected right now. Please try again later.", "error")
        return redirect(url_for("dash.dashboard"))
    spotify_service.save_tokens(current_user, token_info)
    audit.record(current_user, "spotify_linked")
    db.session.commit()
    flash("Spotify connected.", "success")
    return redirect(url_for("dash.dashboard"))


@bp.route("/history/upload", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("UPLOAD"), methods=["POST"], key_func=user_or_ip)
def upload_history():
    """Show the upload page; on POST, check the archive and import it in the background."""
    if request.method == "GET":
        return render_template("spotify_upload_history.html")

    file = request.files.get("history_zip")
    if not file or not file.filename or not file.filename.lower().endswith(".zip"):
        flash("Choose the .zip file Spotify sent you.", "error")
        return redirect(url_for("spotify.upload_history"))
    if not Run.query.filter_by(user_id=current_user.id).first():
        flash("Sync your runs from Garmin first; songs are matched to runs.", "info")
        return redirect(url_for("spotify.upload_history"))
    if current_user.history_import_state == "importing":
        flash("An import is already running. It will finish shortly.", "info")
        return redirect(url_for("dash.dashboard"))

    path = imports.save_upload(file)
    try:
        imports.check_upload(path)
    except HistoryArchiveError as error:
        imports.discard(path)
        flash(str(error), "error")
        return redirect(url_for("spotify.upload_history"))
    imports.start_background_import(current_app._get_current_object(), current_user.id, path)
    flash(
        "Importing your listening history. Matched songs appear as soon as it finishes.", "success"
    )
    return redirect(url_for("dash.dashboard"))
