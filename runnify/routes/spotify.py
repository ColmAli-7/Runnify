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
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services import spotify as spotify_service
from runnify.services.fit import read_fit_to_series
from runnify.services.history_import import import_history_zip_overlapping_runs
from runnify.services.scoring import score_segment

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
    db.session.commit()
    flash("Spotify connected.", "success")
    return redirect(url_for("dash.dashboard"))


@bp.route("/history/upload", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("UPLOAD"), methods=["POST"], key_func=user_or_ip)
def upload_history():
    """Show the upload page; on POST, import a Spotify history ``.zip`` and score matched songs."""
    if request.method == "GET":
        return render_template("spotify_upload_history.html")  # upload page

    file = request.files.get("history_zip")
    if not file or not file.filename.lower().endswith(".zip"):
        abort(400, description="Please upload a .zip file from Spotify")

    zip_bytes = file.read()  # read uploaded zip file

    # match streaming history with run data and analyse performance
    stats = import_history_zip_overlapping_runs(
        zip_bytes=zip_bytes,  # zip file containing spotify listening data
        user_id=current_user.id,
        db=db,
        RunModel=Run,
        SongModel=Song,
        UserSongHistoryModel=UserSongHistory,
        RunSongAnalysisModel=RunSongAnalysis,
        read_fit_to_series=read_fit_to_series,  # converts garmin fit files to data series
        score_segment=score_segment,  # scores each matched song segment
        batch_size=current_app.config.get("HISTORY_BATCH_SIZE", 1000),
        min_overlap_seconds=current_app.config.get("HISTORY_MIN_OVERLAP_SECONDS", 1),
    )

    if stats["note"]:
        flash(stats["note"], "info")
    else:
        flash(f"Matched {stats['saved']} song plays to your runs.", "success")
    return redirect(url_for("dash.dashboard"))  # go back to dashboard after upload
