"""Account management: change display name or password, sign out other devices."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user

from runnify.extensions import db, limiter
from runnify.forms import ChangeNameForm, ChangePasswordForm, first_error
from runnify.security.passwords import hash_password, password_problems, verify_password
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services.notifications import send_password_changed

bp = Blueprint("manage", __name__)  # user account management routes


@bp.route("/manage", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), methods=["POST"], key_func=user_or_ip)
def managing():
    """Show account settings; on POST, change name or password after re-checking the current password."""
    name_form, password_form = ChangeNameForm(), ChangePasswordForm()
    if request.method == "POST" and request.form.get("action") == "sign_out_everywhere":
        _restart_sessions()
        flash("You've been signed out on every other device.", "success")
        return redirect(url_for("manage.managing"))
    if request.method == "POST":
        form = name_form if request.form.get("action") == "change_name" else password_form
        if not form.validate():
            flash(first_error(form), "error")
        elif not verify_password(current_user.password_hash, form.password.data)[0]:
            flash("Your current password is incorrect.", "error")
        elif form is name_form:
            current_user.name = form.new_name.data
            db.session.commit()
            flash("Name updated", "success")
        elif problems := password_problems(
            form.new_password.data, email=current_user.email, name=current_user.name
        ):
            flash(problems[0], "error")
        else:
            current_user.password_hash = hash_password(form.new_password.data)
            _restart_sessions()
            send_password_changed(current_user)
            flash("Password updated. You've been signed out on every other device.", "success")
        return redirect(url_for("manage.managing"))
    return render_template("manage.html", name_form=name_form, password_form=password_form)


def _restart_sessions():
    """Rotate the session token (ending every other session) and re-issue this one."""
    current_user.rotate_session_token()
    db.session.commit()
    login_user(current_user._get_current_object())
