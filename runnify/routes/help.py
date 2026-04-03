from flask import Blueprint, render_template
from flask_login import login_required

help = Blueprint("help", __name__)

@help.route("/help/spotify-upload-guide")
@login_required
def spotify_upload_guide():
    return render_template("spotify_upload_guide.html")
