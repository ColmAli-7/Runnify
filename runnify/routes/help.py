"""Help pages and user guides."""

from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint("help", __name__)

@bp.route("/help/spotify-upload-guide")
@login_required
def spotify_upload_guide():
    """Show the step-by-step guide for requesting Spotify extended streaming history."""
    return render_template("spotify_upload_guide.html")
