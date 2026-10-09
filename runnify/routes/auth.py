"""Authentication: login, registration, logout and password reset by email."""

import time

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from runnify.extensions import db, limiter
from runnify.forms import (
    ForgotPasswordForm,
    LoginForm,
    RegisterForm,
    ResetPasswordForm,
    TwoFactorLoginForm,
    first_error,
)
from runnify.models import User, utcnow
from runnify.security.lockout import clear_failures, is_locked, record_failure
from runnify.security.passwords import hash_password, password_problems, verify_password
from runnify.security.rate_limits import limit_from_config
from runnify.security.redirects import safe_next_url
from runnify.security.tokens import make_reset_token, user_from_reset_token
from runnify.security.two_factor import accept_code, remaining_recovery_codes, use_recovery_code
from runnify.services.notifications import (
    send_lockout_notice,
    send_password_changed,
    send_password_reset,
)

bp = Blueprint("auth", __name__)  # handles auth routes

LOGIN_FAILED = "That email and password combination didn't work."


def _home():
    return url_for("dash.dashboard")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(limit_from_config("LOGIN"), methods=["POST"])
def login():
    """Show the login form; on POST, verify credentials and start a session.

    After signing in the user goes to ``?next=`` when it is a local path,
    otherwise to the dashboard.
    """
    if current_user.is_authenticated:
        return redirect(_home())
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and is_locked(user):
            verify_password(None, form.password.data)  # same timing; the password is not checked
            flash(LOGIN_FAILED, "error")
            return render_template("login.html", form_type="login", form=form)
        matches, needs_rehash = verify_password(
            user.password_hash if user else None, form.password.data
        )
        if matches:
            if needs_rehash:  # upgrade legacy or outdated hashes now that we know the password
                user.password_hash = hash_password(form.password.data)
            next_url = safe_next_url(request.args.get("next"))
            if user.two_factor_enabled:
                db.session.commit()
                session[PENDING_2FA_KEY] = {
                    "uid": user.id,
                    "token": user.session_token,
                    "remember": bool(form.remember.data),
                    "next": next_url,
                    "expires": time.time() + PENDING_2FA_SECONDS,
                }
                return redirect(url_for("auth.verify_two_factor"))
            return _complete_login(user, form.remember.data, next_url)
        if user and record_failure(user):
            send_lockout_notice(user)
        db.session.commit()
        flash(LOGIN_FAILED, "error")
    elif form.errors:
        flash(first_error(form), "error")
    return render_template("login.html", form_type="login", form=form)


def _complete_login(user, remember, next_url):
    """Start the session once every sign-in step has passed."""
    clear_failures(user)
    user.last_login_at = utcnow()
    db.session.commit()
    session.clear()  # nothing from before sign-in carries over into the session
    login_user(user, remember=remember)
    return redirect(next_url or _home())


PENDING_2FA_KEY = "pending_two_factor"
PENDING_2FA_SECONDS = 300


def _pending_two_factor_user():
    """The user who passed the password step and owes a code, if still valid."""
    pending = session.get(PENDING_2FA_KEY)
    if not pending or pending.get("expires", 0) < time.time():
        return None, None
    user = db.session.get(User, pending.get("uid"))
    if user is None or user.session_token != pending.get("token") or not user.two_factor_enabled:
        return None, None
    return user, pending


@bp.route("/login/verify", methods=["GET", "POST"])
@limiter.limit(limit_from_config("LOGIN"), methods=["POST"])
def verify_two_factor():
    """Second sign-in step: a code from the authenticator app, or a recovery code.

    Wrong codes count towards the account lockout, so the six digits can't be
    brute-forced.
    """
    user, pending = _pending_two_factor_user()
    if user is None:
        session.pop(PENDING_2FA_KEY, None)
        flash("Your sign-in timed out. Please sign in again.", "info")
        return redirect(url_for("auth.login"))
    form = TwoFactorLoginForm()
    if form.validate_on_submit():
        if is_locked(user):
            flash("That code didn't work.", "error")
            return render_template("two_factor_verify.html", form=form)
        used_recovery = False
        if not accept_code(user, form.code.data):
            used_recovery = use_recovery_code(user, form.code.data)
            if not used_recovery:
                if record_failure(user):
                    send_lockout_notice(user)
                db.session.commit()
                flash("That code didn't work.", "error")
                return render_template("two_factor_verify.html", form=form)
        response = _complete_login(user, pending["remember"], pending["next"])
        if used_recovery:
            left = remaining_recovery_codes(user)
            flash(f"You used a recovery code; {left} left. Create new ones in Settings.", "info")
        return response
    if form.errors:
        flash(first_error(form), "error")
    return render_template("two_factor_verify.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(limit_from_config("REGISTER"), methods=["POST"])
def register():
    """Show the registration form; on POST, validate and create a new account."""
    if current_user.is_authenticated:
        return redirect(_home())
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():  # check duplicate
            flash("That email is already registered.", "error")
        else:
            user = User(
                name=form.name.data,
                email=form.email.data,
                password_hash=hash_password(form.password.data),
            )
            db.session.add(user)
            db.session.commit()
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))
    elif form.errors:
        flash(first_error(form), "error")
    return render_template("login.html", form_type="register", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """End the current session and return to the login page."""
    logout_user()  # end session
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


RESET_TOKEN_KEY = "password_reset_token"  # noqa: S105  (a session key name, not a secret)


@bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit(limit_from_config("PASSWORD_RESET"), methods=["POST"])
def forgot_password():
    """Show the forgot-password form; on POST, email a single-use reset link.

    The response is the same whether or not the email has an account, so the
    form cannot be used to find out who is registered.
    """
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset(user, make_reset_token(user))
        minutes = current_app.config["PASSWORD_RESET_MAX_AGE"] // 60
        flash(
            f"If an account exists for {form.email.data}, we've emailed it a reset link. "
            f"The link expires in {minutes} minutes.",
            "info",
        )
        return redirect(url_for("auth.login"))
    if form.errors:
        flash(first_error(form), "error")
    return render_template("forgot.html", form=form)


@bp.route("/reset/<token>")
def reset_password(token):
    """Landing point for the emailed link.

    A valid token is moved into the session and the browser is redirected to a
    URL without it, so the token doesn't linger in history, logs or referrers.
    """
    if user_from_reset_token(token) is None:
        flash("That reset link is invalid, already used or expired. Request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))
    session[RESET_TOKEN_KEY] = token
    return redirect(url_for("auth.choose_new_password"))


@bp.route("/reset", methods=["GET", "POST"])
@limiter.limit(limit_from_config("PASSWORD_RESET"), methods=["POST"])
def choose_new_password():
    """Choose a new password for the account named by the reset token in the session."""
    user = user_from_reset_token(session.get(RESET_TOKEN_KEY))
    if user is None:
        session.pop(RESET_TOKEN_KEY, None)
        flash("That reset link is invalid, already used or expired. Request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        problems = password_problems(form.password.data, email=user.email, name=user.name)
        if problems:
            flash(problems[0], "error")
        else:
            user.password_hash = hash_password(form.password.data)
            clear_failures(user)  # a reset also lifts any lockout
            user.rotate_session_token()  # signs out every device and voids the reset link
            db.session.commit()
            session.pop(RESET_TOKEN_KEY, None)
            send_password_changed(user)
            flash("Your password has been reset. Sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
    elif form.errors:
        flash(first_error(form), "error")
    return render_template("reset.html", form=form)
