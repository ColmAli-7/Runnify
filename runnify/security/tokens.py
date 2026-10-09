"""Signed, single-use password-reset tokens.

A token carries the user id and a fingerprint of the account's current
password hash and session token. Any password change or session rotation
changes the fingerprint, so a token stops working once it has been used (or
the password changed some other way), on top of its expiry time.
"""

import hashlib
import hmac

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer

from runnify.extensions import db
from runnify.models import User

RESET_SALT = "runnify.password-reset"


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=RESET_SALT)


def _fingerprint(user):
    material = f"{user.session_token}:{user.password_hash}".encode()
    return hashlib.sha256(material).hexdigest()[:32]


def make_reset_token(user):
    """Return a password-reset token for ``user``."""
    return _serializer().dumps({"uid": user.id, "fp": _fingerprint(user)})


def user_from_reset_token(token):
    """Return the user a reset token belongs to, or ``None`` if it is invalid, expired or used."""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=current_app.config["PASSWORD_RESET_MAX_AGE"])
    except BadSignature:  # also covers SignatureExpired
        return None
    user = db.session.get(User, data.get("uid")) if isinstance(data, dict) else None
    if user is None or not hmac.compare_digest(str(data.get("fp", "")), _fingerprint(user)):
        return None
    return user
