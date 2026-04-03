from flask import Blueprint, request, render_template, redirect, url_for, flash, current_app
from flask_login import login_required
from models import db, User   




playlist = Blueprint("playlist", __name__)


@playlist.route("/playlist", methods=["GET", "POST"])
@login_required
def playlists():
    if request.method == "POST":
        run_type = request.form.get("type")
        pace = request.form.get("pace")
        length = request.form.get("length")
        mood = request.form.get("mood")
        #  make playlist here
        print(f"Generate playlist: {run_type}, {pace}, {length}min, {mood}")
        # flash and redirect to dashboard
    return render_template("playlist.html")