"""Account management: name, password, two-step verification and signed-in devices."""

import json

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from runnify.extensions import db, limiter
from runnify.forms import (
    ChangeNameForm,
    ChangePasswordForm,
    DeleteAccountForm,
    PasswordConfirmForm,
    TwoFactorDisableForm,
    TwoFactorEnableForm,
    first_error,
)
from runnify.security import audit, two_factor
from runnify.security.passwords import hash_password, password_problems, verify_password
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services import account as account_service
from runnify.services.notifications import (
    send_account_deleted,
    send_password_changed,
    send_two_factor_changed,
)

bp = Blueprint("settings", __name__)  # user account management routes

SETUP_SECRET_KEY = "two_factor_setup_secret"  # noqa: S105  (a session key name, not a secret)


@bp.route("/settings", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), methods=["POST"], key_func=user_or_ip)
def index():
    """Show account settings; on POST, change name or password after re-checking the current password."""
    name_form, password_form = ChangeNameForm(), ChangePasswordForm()
    if request.method == "POST" and request.form.get("action") == "sign_out_everywhere":
        audit.record(current_user, "sessions_revoked")
        _restart_sessions()
        flash("You've been signed out on every other device.", "success")
        return redirect(url_for("settings.index"))
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
            audit.record(current_user, "password_changed")
            _restart_sessions()
            send_password_changed(current_user)
            flash("Password updated. You've been signed out on every other device.", "success")
        return redirect(url_for("settings.index"))
    return render_template(
        "manage.html",
        name_form=name_form,
        password_form=password_form,
        export_form=PasswordConfirmForm(),
        delete_form=DeleteAccountForm(),
        activity=audit.recent(current_user),
    )


def _restart_sessions():
    """Rotate the session token (ending every other session) and re-issue this one."""
    current_user.rotate_session_token()
    db.session.commit()
    login_user(current_user._get_current_object())


@bp.route("/settings/two-factor", methods=["GET", "POST"], endpoint="two_factor")
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), methods=["POST"], key_func=user_or_ip)
def two_factor_settings():
    """Set up two-step verification, or manage it once it is on.

    Setting up shows a QR code for a new secret; scanning it and entering a
    code (plus the password) proves the app works before anything is saved.
    """
    if current_user.two_factor_enabled:
        return render_template(
            "two_factor_manage.html",
            remaining=two_factor.remaining_recovery_codes(current_user),
            disable_form=TwoFactorDisableForm(),
            codes_form=PasswordConfirmForm(),
        )
    secret = session.get(SETUP_SECRET_KEY) or two_factor.new_secret()
    session[SETUP_SECRET_KEY] = secret
    form = TwoFactorEnableForm()
    if form.validate_on_submit():
        if not verify_password(current_user.password_hash, form.password.data)[0]:
            flash("Your current password is incorrect.", "error")
        elif not two_factor.accept_code(current_user, form.code.data, secret=secret):
            flash("That code didn't work. Check your phone sets its time automatically.", "error")
        else:
            codes = two_factor.enable(current_user, secret)
            audit.record(current_user, "two_factor_enabled")
            session.pop(SETUP_SECRET_KEY, None)
            _restart_sessions()  # also commits
            send_two_factor_changed(current_user, enabled=True)
            flash("Two-step verification is on. Other devices were signed out.", "success")
            return render_template("recovery_codes.html", codes=codes)
    elif form.errors:
        flash(first_error(form), "error")
    uri = two_factor.provisioning_uri(secret, current_user.email)
    return render_template(
        "two_factor_setup.html",
        form=form,
        qr_svg=two_factor.qr_svg(uri),
        secret=two_factor.format_secret(secret),
    )


@bp.route("/settings/two-factor/disable", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), key_func=user_or_ip)
def disable_two_factor():
    """Turn two-step verification off (password plus a current or recovery code)."""
    form = TwoFactorDisableForm()
    if not form.validate_on_submit():
        flash(first_error(form), "error")
    elif not verify_password(current_user.password_hash, form.password.data)[0]:
        flash("Your current password is incorrect.", "error")
    elif not (
        two_factor.accept_code(current_user, form.code.data)
        or two_factor.use_recovery_code(current_user, form.code.data)
    ):
        flash("That code didn't work.", "error")
    else:
        two_factor.disable(current_user)
        audit.record(current_user, "two_factor_disabled")
        db.session.commit()
        send_two_factor_changed(current_user, enabled=False)
        flash("Two-step verification is off.", "info")
    return redirect(url_for("settings.two_factor"))


@bp.route("/settings/two-factor/recovery-codes", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), key_func=user_or_ip)
def new_recovery_codes():
    """Replace the recovery codes (password required); the new ones are shown once."""
    if not current_user.two_factor_enabled:
        return redirect(url_for("settings.two_factor"))
    form = PasswordConfirmForm()
    if (
        not form.validate_on_submit()
        or not verify_password(current_user.password_hash, form.password.data)[0]
    ):
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("settings.two_factor"))
    codes = two_factor.replace_recovery_codes(current_user)
    audit.record(current_user, "recovery_codes_replaced")
    db.session.commit()
    return render_template("recovery_codes.html", codes=codes)


@bp.route("/settings/export", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), key_func=user_or_ip)
def export_data():
    """Download everything Runnify holds about the user as JSON (password required)."""
    form = PasswordConfirmForm()
    if (
        not form.validate_on_submit()
        or not verify_password(current_user.password_hash, form.password.data)[0]
    ):
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("settings.index"))
    payload = account_service.export_data(current_user)
    audit.record(current_user, "data_exported")
    db.session.commit()
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="runnify-data.json"'},
    )


@bp.route("/settings/delete", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("ACCOUNT_CHANGE"), key_func=user_or_ip)
def delete_account():
    """Permanently delete the account and all personal data (password + confirmation)."""
    form = DeleteAccountForm()
    if not form.validate_on_submit():
        flash(first_error(form), "error")
        return redirect(url_for("settings.index"))
    if not verify_password(current_user.password_hash, form.password.data)[0]:
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("settings.index"))
    user = current_user._get_current_object()
    send_account_deleted(user)
    account_service.delete_account(user)
    db.session.commit()
    logout_user()
    session.clear()
    flash("Your account and all of its data have been deleted.", "info")
    return redirect(url_for("main.home"))
