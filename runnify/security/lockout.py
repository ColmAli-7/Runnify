"""Account lockout after repeated failed sign-ins.

IP rate limits slow down one attacker; lockout protects one account from many
(e.g. a botnet guessing from thousands of addresses). While an account is
locked its password is not checked at all. The on-screen message stays the
same as for a wrong password, so lockouts cannot be used to discover which
emails are registered; the account owner is told by email instead.
"""

from datetime import timedelta

from flask import current_app

from runnify.models import utcnow

MAX_LOCK = timedelta(hours=24)


def is_locked(user):
    """Return ``True`` while ``user`` is locked out."""
    return bool(user.locked_until and user.locked_until > utcnow())


def record_failure(user):
    """Count a failed sign-in for ``user`` and lock the account if it crossed the threshold.

    Returns:
        ``True`` when this failure newly locked the account (time to notify the owner).
    """
    threshold = current_app.config["LOGIN_LOCKOUT_THRESHOLD"]
    user.failed_login_count = (user.failed_login_count or 0) + 1
    excess = user.failed_login_count - threshold
    if excess < 0:
        return False
    minutes = current_app.config["LOGIN_LOCKOUT_MINUTES"] * 2 ** min(excess, 10)
    user.locked_until = utcnow() + min(timedelta(minutes=minutes), MAX_LOCK)
    return excess == 0


def clear_failures(user):
    """Reset the failure count and lift any lock (successful sign-in or password reset)."""
    user.failed_login_count = 0
    user.locked_until = None
