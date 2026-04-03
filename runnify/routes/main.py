from flask import Blueprint, render_template
from flask_login import current_user

main = Blueprint("main", __name__)  # main site routes

@main.route("/")
def home():
    if current_user.is_authenticated:  # show personalised home if logged in
        return render_template("index.html", user=current_user)
    return render_template("index.html")  # default homepage for visitors
