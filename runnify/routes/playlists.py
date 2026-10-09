"""Playlist generator (work in progress: the form is captured but no playlist is built yet)."""

from flask import Blueprint, render_template, request
from flask_login import login_required

bp = Blueprint("playlist", __name__)


@bp.route("/playlist", methods=["GET", "POST"])
@login_required
def playlists():
    """Show the playlist form; on POST, read run type, pace, length and mood (generation not yet implemented)."""
    if request.method == "POST":
        run_type = request.form.get("type")
        pace = request.form.get("pace")
        length = request.form.get("length")
        mood = request.form.get("mood")
        #  make playlist here
        print(f"Generate playlist: {run_type}, {pace}, {length}min, {mood}")
        # flash and redirect to dashboard
    return render_template("playlist.html")
