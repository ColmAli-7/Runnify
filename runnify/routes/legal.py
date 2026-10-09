"""Legal pages (privacy, terms, cookies) and the consent step for existing accounts."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from runnify.extensions import db
from runnify.forms import ConsentForm, first_error
from runnify.security.redirects import safe_next_url

bp = Blueprint("legal", __name__)

# endpoints a signed-in user without current consent may still use
CONSENT_EXEMPT = {
    "static",
    "legal.privacy",
    "legal.terms",
    "legal.cookies",
    "legal.consent",
    "auth.logout",
    "manage.export_data",
    "manage.delete_account",
    "manage.managing",
}


@bp.route("/privacy")
def privacy():
    """The privacy policy."""
    return render_template("legal/privacy.html")


@bp.route("/terms")
def terms():
    """The terms of use."""
    return render_template("legal/terms.html")


@bp.route("/cookies")
def cookies():
    """The cookie policy."""
    return render_template("legal/cookies.html")


@bp.before_app_request
def require_current_consent():
    """Send signed-in users who haven't agreed to the current policies to the consent step."""
    if (
        current_user.is_authenticated
        and request.endpoint not in CONSENT_EXEMPT
        and not current_user.has_current_consent
    ):
        return redirect(url_for("legal.consent", next=request.full_path.rstrip("?")))
    return None


@bp.route("/consent", methods=["GET", "POST"])
@login_required
def consent():
    """Ask an existing user to agree to the current terms and data processing."""
    if current_user.has_current_consent:
        return redirect(url_for("dash.dashboard"))
    form = ConsentForm()
    if form.validate_on_submit():
        current_user.record_consent()
        db.session.commit()
        return redirect(safe_next_url(request.args.get("next")) or url_for("dash.dashboard"))
    if form.errors:
        flash(first_error(form), "error")
    return render_template("legal/consent.html", form=form)
