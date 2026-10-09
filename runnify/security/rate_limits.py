"""Rate limits for endpoints an attacker could abuse.

Limits are read from config at request time (``RATE_LIMIT_*``), so they can be
tuned per environment. Anonymous requests are counted per client IP; signed-in
requests per account, so one user cannot be locked out by their neighbours on a
shared network.
"""

from flask import current_app
from flask_limiter.util import get_remote_address
from flask_login import current_user


def user_or_ip():
    """Rate-limit key: the signed-in user's id, otherwise the client IP."""
    if current_user.is_authenticated:
        return f"user:{current_user.get_id()}"
    return f"ip:{get_remote_address()}"


def limit_from_config(name):
    """Return a callable that reads the limit string ``RATE_LIMIT_<NAME>`` from config."""
    return lambda: current_app.config[f"RATE_LIMIT_{name}"]
