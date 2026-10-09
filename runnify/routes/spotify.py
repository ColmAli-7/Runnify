"""Spotify integration (mounted under ``/spotify``).

Handles the Spotify OAuth flow and the upload of a user's extended streaming
history zip. OAuth settings come from the app's ``SPOTIFY_*`` config values.
"""

import time

import spotipy
from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from spotipy.oauth2 import SpotifyOAuth

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, User, UserSongHistory
from runnify.services.fit import read_fit_to_series
from runnify.services.history_import import import_history_zip_overlapping_runs
from runnify.services.scoring import score_segment

bp = Blueprint("spotify", __name__)  # spotify integration routes


def _oauth():
    """Return a ``SpotifyOAuth`` helper configured from the app's ``SPOTIFY_*`` settings."""
    config = current_app.config
    return SpotifyOAuth(
        client_id=config["SPOTIFY_CLIENT_ID"],
        client_secret=config["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=config["SPOTIFY_REDIRECT_URI"],
        scope=config["SPOTIFY_SCOPE"],
    )


@bp.route("/login")
@login_required
def login_spotify():
    """Redirect the user to Spotify's authorisation page."""
    return redirect(_oauth().get_authorize_url())  # redirect to spotify login


@bp.route("/callback")
@login_required
def callback():
    """OAuth redirect target: exchange the code for tokens and store them on the user."""
    code = request.args.get("code")  # code returned after user authorises app
    token_info = _oauth().get_access_token(code)  # exchange code for tokens
    sp = spotipy.Spotify(auth=token_info["access_token"])
    profile = sp.current_user()  # get user profile from spotify
    user = db.session.get(User, current_user.id)
    user.spotify_token = token_info["access_token"]
    user.spotify_refresh_token = token_info["refresh_token"]
    user.spotify_expires_at = token_info["expires_at"]
    db.session.commit()  # store spotify tokens
    return redirect(url_for("dash.dashboard"))


def get_spotify_client(user: User):
    """Return an authenticated ``spotipy.Spotify`` client for ``user``.

    Refreshes and saves the access token if it expires within 60 seconds.
    Returns ``None`` if the user has not connected Spotify.
    """
    if not user.spotify_token or not user.spotify_refresh_token:
        return None
    if user.spotify_expires_at - int(time.time()) < 60:  # refresh if token about to expire
        refreshed = _oauth().refresh_access_token(user.spotify_refresh_token)
        user.spotify_token = refreshed["access_token"]
        user.spotify_refresh_token = refreshed.get("refresh_token", user.spotify_refresh_token)
        user.spotify_expires_at = refreshed["expires_at"]
        db.session.commit()
    return spotipy.Spotify(auth=user.spotify_token)


@bp.route("/history/upload", methods=["GET", "POST"])
@login_required
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

    # stats includes counts of processed runs, matched songs, and created analyses

    return redirect(url_for("dash.dashboard"))  # go back to dashboard after upload
