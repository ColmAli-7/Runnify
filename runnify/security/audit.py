"""The account security activity log (see :class:`runnify.models.SecurityEvent`)."""

import ipaddress
from datetime import timedelta

from flask import has_request_context, request

from runnify.extensions import db
from runnify.models import SecurityEvent, utcnow

RETENTION = timedelta(days=90)

DESCRIPTIONS = {
    "account_created": "Account created",
    "sign_in": "Signed in",
    "sign_in_failed": "Failed sign-in attempt",
    "account_locked": "Sign-in paused after failed attempts",
    "password_changed": "Password changed",
    "password_reset": "Password reset by email",
    "sessions_revoked": "Signed out of other devices",
    "two_factor_enabled": "Two-step verification turned on",
    "two_factor_disabled": "Two-step verification turned off",
    "recovery_code_used": "Recovery code used to sign in",
    "recovery_codes_replaced": "New recovery codes created",
    "garmin_linked": "Garmin connected",
    "garmin_unlinked": "Garmin disconnected",
    "spotify_linked": "Spotify connected",
    "spotify_unlinked": "Spotify disconnected",
    "data_exported": "Account data downloaded",
}


def anonymise_ip(address):
    """Truncate an IP address to its network (/24 for IPv4, /48 for IPv6)."""
    try:
        ip = ipaddress.ip_address(address)
    except (TypeError, ValueError):
        return None
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False).network_address)


def record(user, kind):
    """Add a ``kind`` event to ``user``'s log (the caller commits)."""
    if kind not in DESCRIPTIONS:
        raise ValueError(f"unknown security event {kind!r}")
    ip_prefix = user_agent = None
    if has_request_context():
        ip_prefix = anonymise_ip(request.remote_addr)
        user_agent = (request.user_agent.string or "")[:160] or None
    db.session.add(
        SecurityEvent(user_id=user.id, kind=kind, ip_prefix=ip_prefix, user_agent=user_agent)
    )
    SecurityEvent.query.filter(
        SecurityEvent.user_id == user.id, SecurityEvent.created_at < utcnow() - RETENTION
    ).delete()


def recent(user, limit=20):
    """``user``'s newest events, as ``(event, description)`` pairs."""
    events = (
        SecurityEvent.query.filter_by(user_id=user.id)
        .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [(event, DESCRIPTIONS[event.kind]) for event in events]
