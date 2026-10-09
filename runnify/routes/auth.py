"""Authentication: login, registration, logout and password reset by email."""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from runnify.extensions import db, limiter
from runnify.forms import (
    ForgotPasswordForm,
    LoginForm,
    RegisterForm,
    ResetPasswordForm,
    first_error,
)
from runnify.models import User, utcnow
from runnify.security.lockout import clear_failures, is_locked, record_failure
from runnify.security.passwords import hash_password, password_problems, verify_password
from runnify.security.rate_limits import limit_from_config
from runnify.security.redirects import safe_next_url
from runnify.services.mail import send_email

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
            clear_failures(user)
            user.last_login_at = utcnow()
            db.session.commit()
            login_user(user, remember=form.remember.data)
            return redirect(safe_next_url(request.args.get("next")) or _home())
        if user and record_failure(user):
            send_lockout_email(user)
        db.session.commit()
        flash(LOGIN_FAILED, "error")
    elif form.errors:
        flash(first_error(form), "error")
    return render_template("login.html", form_type="login", form=form)


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


def send_lockout_email(user):
    """Tell the account owner that sign-in was paused after repeated failures."""
    until = user.locked_until.strftime("%H:%M UTC on %d %b %Y")
    send_email(
        user.email,
        "Runnify: sign-in paused after failed attempts",
        f"""Hello {user.name},

Several attempts to sign in to your Runnify account used the wrong password, so
sign-in is paused until {until}.

If that was you, wait until then or reset your password to get back in straight
away: {_external_url("auth.forgot_password")}

If it wasn't you, someone may be trying to guess your password. Your account is
safe while sign-in is paused; consider choosing a new, unique password.""",
    )


def _external_url(endpoint, **values):
    """Absolute URL for emails, built from PUBLIC_BASE_URL rather than the request's Host header."""
    base = current_app.config.get("PUBLIC_BASE_URL")
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def generate_reset_token(email):
    """Return a signed, timestamped password-reset token encoding ``email``."""
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])  # create serialiser
    return s.dumps(email, salt="password-reset")  # encode email as token


def verify_reset_token(token, max_age=3600):
    """Return the email inside a reset token, or ``None`` if it is invalid or older than ``max_age`` seconds."""
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = s.loads(token, salt="password-reset", max_age=max_age)  # decode token
        return email
    except (SignatureExpired, BadSignature):
        return None  # invalid or expired token


def send_reset_email(to_email, reset_link):
    """Email a password-reset link."""
    send_email(
        to_email,
        "Runnify Password Reset",
        f"""Hello,

We received a request to reset your Runnify password.

To reset your password, click the link below:
{reset_link}

If you didn't request this, please ignore this email.""",
    )


@bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit(limit_from_config("PASSWORD_RESET"), methods=["POST"])
def forgot_password():
    """Show the forgot-password form; on POST, email a reset link (valid for 1 hour)."""
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if not user:  # email not found
            flash("That email is not registered.", "error")
            return render_template("forgot.html", form=form)
        token = generate_reset_token(user.email)  # create token
        reset_link = url_for("auth.reset_password", token=token, _external=True)  # build reset link
        send_reset_email(user.email, reset_link)  # send email
        flash("A reset link has been sent to your email.", "info")
        return redirect(url_for("auth.login"))
    if form.errors:
        flash(first_error(form), "error")
    return render_template("forgot.html", form=form)


@bp.route("/reset/<token>", methods=["GET", "POST"])
@limiter.limit(limit_from_config("PASSWORD_RESET"), methods=["POST"])
def reset_password(token):
    """Validate a reset token and, on POST, set the user's new password."""
    email = verify_reset_token(token)  # validate token
    if not email:
        flash("The reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    user = User.query.filter_by(email=email).first_or_404()
    form = ResetPasswordForm()
    if form.validate_on_submit():
        problems = password_problems(form.password.data, email=user.email, name=user.name)
        if problems:
            flash(problems[0], "error")
        else:
            user.password_hash = hash_password(form.password.data)  # update password
            db.session.commit()
            flash("Password reset successful. Please log in.", "success")
            return redirect(url_for("auth.login"))
    elif form.errors:
        flash(first_error(form), "error")
    return render_template("reset.html", token=token, form=form)
