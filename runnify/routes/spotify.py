"""Spotify OAuth (mounted under ``/spotify``; the callback URL is registered with Spotify).

OAuth details live in :mod:`runnify.services.spotify`.
"""

import hmac
import logging
import secrets

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from runnify.extensions import db
from runnify.security import audit
from runnify.services import spotify as spotify_service

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
        return redirect(url_for("connections.index"))
    if request.args.get("error"):
        flash("Spotify wasn't connected.", "info")
        return redirect(url_for("connections.index"))
    code = request.args.get("code")
    if not code:
        abort(400)
    try:
        token_info = spotify_service.exchange_code(code)
    except Exception:
        logger.exception("Spotify token exchange failed")
        flash("Spotify couldn't be connected right now. Please try again later.", "error")
        return redirect(url_for("connections.index"))
    spotify_service.save_tokens(current_user, token_info)
    audit.record(current_user, "spotify_linked")
    db.session.commit()
    flash("Spotify connected. You can now save playlists to it.", "success")
    return redirect(url_for("connections.index"))
