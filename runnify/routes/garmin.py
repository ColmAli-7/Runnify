"""Garmin Connect account linking and syncing.

The Garmin password is used once, to sign in, and is never stored; see
:mod:`runnify.services.garmin`.
"""

from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required

from runnify.extensions import db, limiter
from runnify.forms import GarminCodeForm, GarminConnectForm, first_error
from runnify.security import audit
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services import garmin as garmin_service

bp = Blueprint("garmin", __name__)  # garmin connection routes

PENDING_KEY = "garmin_pending_login"


def _render(form=None, code_form=None, awaiting_code=False):
    return render_template(
        "garmin.html",
        form=form or GarminConnectForm(),
        code_form=code_form or GarminCodeForm(),
        awaiting_code=awaiting_code,
    )


def _linked():
    audit.record(current_user, "garmin_linked")
    db.session.commit()
    garmin_service.start_background_sync(current_app._get_current_object(), current_user.id)
    flash("Garmin connected. Your runs are syncing in the background.", "success")
    return redirect(url_for("garmin.garmin"))


@bp.route("/garmin", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("GARMIN_CONNECT"), methods=["POST"], key_func=user_or_ip)
def garmin():
    """Show Garmin status; on POST, sign in to Garmin to link the account.

    If Garmin asks for a two-step verification code, the code form is shown and
    the sign-in waits (for five minutes) in :data:`garmin_service.pending_logins`.
    """
    form = GarminConnectForm()
    if form.validate_on_submit():
        try:
            pending = garmin_service.begin_link(current_user, form.email.data, form.password.data)
        except garmin_service.GarminError as error:
            flash(str(error), "error")
            return _render(form)
        if pending:
            session[PENDING_KEY] = pending
            return _render(awaiting_code=True)
        return _linked()
    if form.errors:
        flash(first_error(form), "error")
    return _render(form)


@bp.route("/garmin/verify", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("GARMIN_CONNECT"), key_func=user_or_ip)
def verify():
    """Finish linking with Garmin's two-step verification code."""
    code_form = GarminCodeForm()
    if not code_form.validate_on_submit():
        flash(first_error(code_form), "error")
        return _render(code_form=code_form, awaiting_code=True)
    try:
        garmin_service.finish_link(current_user, session.pop(PENDING_KEY, ""), code_form.code.data)
    except garmin_service.GarminError as error:
        flash(str(error), "error")
        return redirect(url_for("garmin.garmin"))
    return _linked()


@bp.route("/garmin/sync", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("GARMIN_SYNC"), key_func=user_or_ip)
def sync_now():
    """Start a fresh sync of new Garmin runs."""
    if not (current_user.garmin_tokens or current_user.garmin_password):
        flash("Connect Garmin first.", "error")
    elif current_user.garmin_sync_state == "syncing":
        flash("A sync is already running.", "info")
    else:
        garmin_service.start_background_sync(current_app._get_current_object(), current_user.id)
        flash("Syncing new runs from Garmin.", "success")
    return redirect(url_for("garmin.garmin"))


@bp.route("/garmin/disconnect", methods=["POST"])
@login_required
def disconnect():
    """Unlink Garmin. Runs already imported are kept."""
    garmin_service.unlink(current_user)
    audit.record(current_user, "garmin_unlinked")
    db.session.commit()
    flash("Garmin disconnected. Runs you already imported are kept.", "info")
    return redirect(url_for("garmin.garmin"))
