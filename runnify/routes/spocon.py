import os, time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import (
    Blueprint,
    redirect,
    request,
    session,
    url_for,
    render_template,
    current_app,
    abort,
)
from flask_login import current_user, login_required
from models import db, User, Run, Song, UserSongHistory, RunSongAnalysis
from dotenv import load_dotenv
from functions.history_overlap import import_history_zip_overlapping_runs
from functions.fit_util import read_fit_to_series
from .get_activities import _score_segment

load_dotenv()
spocon = Blueprint("spotify", __name__)  # spotify integration routes

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SCOPE = os.getenv("SPOTIFY_SCOPE")

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
)  # setup oauth credentials


@spocon.route("/login")
@login_required
def login_spotify():
    return redirect(sp_oauth.get_authorize_url())  # redirect to spotify login


@spocon.route("/callback")
@login_required
def callback():
    code = request.args.get("code")  # code returned after user authorises app
    token_info = sp_oauth.get_access_token(code)  # exchange code for tokens
    sp = spotipy.Spotify(auth=token_info["access_token"])
    profile = sp.current_user()  # get user profile from spotify
    user = User.query.get(current_user.id)
    user.spotify_token = token_info["access_token"]
    user.spotify_refresh_token = token_info["refresh_token"]
    user.spotify_expires_at = token_info["expires_at"]
    db.session.commit()  # store spotify tokens
    return redirect(url_for("dash.dashboard"))


def get_spotify_client(user: User):
    if not user.spotify_token or not user.spotify_refresh_token:
        return None
    if (
        user.spotify_expires_at - int(time.time()) < 60
    ):  # refresh if token about to expire
        refreshed = sp_oauth.refresh_access_token(user.spotify_refresh_token)
        user.spotify_token = refreshed["access_token"]
        user.spotify_refresh_token = refreshed.get(
            "refresh_token", user.spotify_refresh_token
        )
        user.spotify_expires_at = refreshed["expires_at"]
        db.session.commit()
    return spotipy.Spotify(auth=user.spotify_token)


@spocon.route("/history/upload", methods=["GET", "POST"])
@login_required
def upload_history():
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
        _score_segment=_score_segment,  # import scoring function
        batch_size=current_app.config.get("HISTORY_BATCH_SIZE", 1000),
        min_overlap_seconds=current_app.config.get("HISTORY_MIN_OVERLAP_SECONDS", 1),
    )

    # stats includes counts of processed runs, matched songs, and created analyses


    return redirect(url_for("dash.dashboard"))  # go back to dashboard after upload
