"""Account emails: password resets and security notifications.

Links are built from ``PUBLIC_BASE_URL`` rather than the request's ``Host``
header, so a forged header can never point a reset email at another site.
"""

from flask import current_app, url_for

from runnify.services.mail import send_email


def external_url(endpoint, **values):
    """Absolute URL for an email link."""
    base = current_app.config.get("PUBLIC_BASE_URL")
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)  # local development only


def send_password_reset(user, token):
    """Email ``user`` a link to choose a new password."""
    minutes = current_app.config["PASSWORD_RESET_MAX_AGE"] // 60
    send_email(
        user.email,
        "Reset your Runnify password",
        f"""Hello {user.name},

Someone (hopefully you) asked to reset the password for your Runnify account.
Choose a new password here (the link works once and expires in {minutes} minutes):

{external_url("auth.reset_password", token=token)}

If you didn't ask for this, you can ignore this email; your password stays the same.""",
    )


def send_password_changed(user):
    """Tell ``user`` their password was changed, in case it wasn't them."""
    send_email(
        user.email,
        "Your Runnify password was changed",
        f"""Hello {user.name},

The password for your Runnify account was just changed, and every other device
was signed out.

If this wasn't you, reset your password straight away:
{external_url("auth.forgot_password")}""",
    )


def send_lockout_notice(user):
    """Tell the account owner that sign-in was paused after repeated failures."""
    until = user.locked_until.strftime("%H:%M UTC on %d %b %Y")
    send_email(
        user.email,
        "Runnify: sign-in paused after failed attempts",
        f"""Hello {user.name},

Several attempts to sign in to your Runnify account used the wrong password, so
sign-in is paused until {until}.

If that was you, wait until then or reset your password to get back in straight
away: {external_url("auth.forgot_password")}

If it wasn't you, someone may be trying to guess your password. Your account is
safe while sign-in is paused; consider choosing a new, unique password.""",
    )


def send_account_deleted(user):
    """Confirm to ``user`` that their account and data were deleted."""
    send_email(
        user.email,
        "Your Runnify account was deleted",
        f"""Hello {user.name},

Your Runnify account and all of its data (runs, song history, scores and
connections) have been permanently deleted.

Thanks for running with us.""",
    )


def send_two_factor_changed(user, enabled):
    """Tell ``user`` that two-step verification was turned on or off."""
    state = "turned on" if enabled else "turned off"
    send_email(
        user.email,
        f"Two-step verification {state} for Runnify",
        f"""Hello {user.name},

Two-step verification was just {state} for your Runnify account.

If this wasn't you, reset your password straight away:
{external_url("auth.forgot_password")}""",
    )
