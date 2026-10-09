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
from flask_login import login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from runnify.extensions import db, limiter
from runnify.models import User
from runnify.security.passwords import hash_password, verify_password
from runnify.security.rate_limits import limit_from_config
from runnify.services.mail import send_email
from runnify.services.passwords import passw_strength

bp = Blueprint("auth", __name__)  # handles auth routes


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(limit_from_config("LOGIN"), methods=["POST"])
def login():
    """Show the login form; on POST, verify credentials and start a session."""
    if request.method == "POST":
        email = request.form.get("email").strip().lower()  # normalise email
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()  # find user
        matches, needs_rehash = verify_password(user.password_hash if user else None, password)
        if not matches:  # invalid login
            flash("Invalid email or password", "error")
            return render_template("login.html", form_type="login")
        if needs_rehash:  # upgrade legacy or outdated hashes now that we know the password
            user.password_hash = hash_password(password)
            db.session.commit()
        login_user(user)  # start user session
        flash("Logged in successfully!", "success")
        return redirect(url_for("dash.dashboard"))  # go to dashboard
    return render_template("login.html", form_type="login")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(limit_from_config("REGISTER"), methods=["POST"])
def register():
    """Show the registration form; on POST, validate and create a new account."""
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")
        strong = passw_strength(password)  # check password strength
        if not strong[0]:
            flash(strong[1][0], strong[1][1])
            return render_template("login.html", form_type="register")
        existing_user = User.query.filter_by(email=email).first()  # check duplicate
        if existing_user:
            flash("That email is already registered.", "error")
            return render_template("login.html", form_type="register")
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
        )
        db.session.add(user)
        db.session.commit()
        flash("Account created! You can now log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("login.html", form_type="register")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """End the current session and return to the login page."""
    logout_user()  # end session
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


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
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:  # email not found
            flash("That email is not registered.", "error")
            return render_template("forgot.html")
        token = generate_reset_token(email)  # create token
        reset_link = url_for("auth.reset_password", token=token, _external=True)  # build reset link
        send_reset_email(email, reset_link)  # send email
        flash("A reset link has been sent to your email.", "info")
        return redirect(url_for("auth.login"))
    return render_template("forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
@limiter.limit(limit_from_config("PASSWORD_RESET"), methods=["POST"])
def reset_password(token):
    """Validate a reset token and, on POST, set the user's new password."""
    email = verify_reset_token(token)  # validate token
    if not email:
        flash("The reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    user = User.query.filter_by(email=email).first_or_404()
    if request.method == "POST":
        new_password = request.form.get("password")
        strong = passw_strength(new_password)  # check strength
        if not strong[0]:
            flash(strong[1][0], strong[1][1])
            return render_template("reset.html", token=token)
        user.password_hash = hash_password(new_password)  # update password
        db.session.commit()
        flash("Password reset successful. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("reset.html", token=token)
