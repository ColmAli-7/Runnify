"""Account management: change display name or password."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from functions.validation import passw_strength

manage = Blueprint("manage", __name__)  # user account management routes


@manage.route("/manage", methods=["GET", "POST"])
@login_required
def managing():
    """Show account settings; on POST, change name or password after re-checking the current password."""
    if request.method == "POST":
        action = request.form.get("action")  # determine what user is changing
        password = request.form.get("password")

        if not check_password_hash(
            current_user.password_hash, password
        ):  # verify password before any change
            flash("Incorrect password", "error")
            return redirect(url_for("manage.managing"))
        
        if action == "change_name":
            new_name = request.form.get("new_name")
            current_user.name = new_name  # update display name
            db.session.commit()
            flash("Name updated", "success")
        else:  # change password
            new_pw = request.form.get("new_password")
            confirm_pw = request.form.get("confirm_password")
            strong = passw_strength(new_pw)  # validate password strength
            if not strong[0]:
                flash(strong[1][0], strong[1][1])
                return redirect(url_for("manage.managing"))
            if new_pw != confirm_pw:  # ensure both inputs match
                flash("Passwords do not match", "error")
                return redirect(url_for("manage.managing"))
            else:
                current_user.password_hash = generate_password_hash(
                    new_pw
                )  # update password
                db.session.commit()
                flash("Password updated", "success")
                return redirect(url_for("manage.managing"))

    return render_template("manage.html")
