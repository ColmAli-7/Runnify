"""Public landing page."""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from runnify.content.sample import landing_sample

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    """The landing page; signed-in runners go straight to their dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("marketing/home.html", sample=landing_sample())
