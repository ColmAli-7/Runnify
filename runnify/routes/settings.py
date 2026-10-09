"""Account management: change display name or password."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from runnify.extensions import db, limiter
from runnify.security.passwords import hash_password, password_problems, verify_password
from runnify.security.rate_limits import limit_from_config, user_or_ip

bp = Blueprint("manage", __name__)  # user account management routes


@bp.route("/manage", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), methods=["POST"], key_func=user_or_ip)
def managing():
    """Show account settings; on POST, change name or password after re-checking the current password."""
    if request.method == "POST":
        action = request.form.get("action")  # determine what user is changing
        password = request.form.get("password")

        if not verify_password(current_user.password_hash, password)[
            0
        ]:  # re-check before any change
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
            problems = password_problems(new_pw, email=current_user.email, name=current_user.name)
            if problems:
                flash(problems[0], "error")
                return redirect(url_for("manage.managing"))
            if new_pw != confirm_pw:  # ensure both inputs match
                flash("Passwords do not match", "error")
                return redirect(url_for("manage.managing"))
            else:
                current_user.password_hash = hash_password(new_pw)  # update password
                db.session.commit()
                flash("Password updated", "success")
                return redirect(url_for("manage.managing"))

    return render_template("manage.html")
