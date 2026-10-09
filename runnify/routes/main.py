"""Public landing page."""

from flask import Blueprint, render_template
from flask_login import current_user

bp = Blueprint("main", __name__)  # main site routes


@bp.route("/")
def home():
    """Render the homepage, personalised when a user is logged in."""
    if current_user.is_authenticated:  # show personalised home if logged in
        return render_template("index.html", user=current_user)
    return render_template("index.html")  # default homepage for visitors
