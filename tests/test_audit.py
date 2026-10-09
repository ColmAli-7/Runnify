"""The security activity log."""

from datetime import timedelta

import pytest

from runnify.extensions import db
from runnify.models import SecurityEvent, User, utcnow
from runnify.security import audit
from tests.conftest import PASSWORD

LOGIN = {"email": "runner@example.com", "password": PASSWORD}


def _kinds(app, user_id):
    with app.app_context():
        return [
            e.kind
            for e in SecurityEvent.query.filter_by(user_id=user_id).order_by(SecurityEvent.id)
        ]


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("203.0.113.77", "203.0.113.0"),
        ("2001:db8:abcd:12::1", "2001:db8:abcd::"),
        ("junk", None),
        (None, None),
    ],
)
def test_ip_addresses_are_truncated(address, expected):
    assert audit.anonymise_ip(address) == expected


def test_sign_ins_and_failures_are_logged(app, client, user):
    client.post("/login", data={**LOGIN, "password": "wrong"})
    client.post("/login", data=LOGIN, environ_base={"REMOTE_ADDR": "198.51.100.23"})
    assert _kinds(app, user) == ["sign_in_failed", "sign_in"]
    with app.app_context():
        assert SecurityEvent.query.filter_by(kind="sign_in").one().ip_prefix == "198.51.100.0"


def test_lockout_is_logged(app, client, user):
    for _ in range(5):
        client.post("/login", data={**LOGIN, "password": "wrong"})
    assert _kinds(app, user)[-2:] == ["sign_in_failed", "account_locked"]


def test_password_change_and_revocation_are_logged(app, auth_client, user):
    new = "a completely new passphrase"
    auth_client.post(
        "/manage", data={"password": PASSWORD, "new_password": new, "confirm_password": new}
    )
    auth_client.post("/manage", data={"action": "sign_out_everywhere"})
    assert _kinds(app, user) == ["password_changed", "sessions_revoked"]


def test_settings_show_recent_activity(app, auth_client, user):
    with app.app_context():
        audit.record(db.session.get(User, user), "password_changed")
        db.session.commit()
    assert b"Password changed" in auth_client.get("/manage").data


def test_old_events_expire(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        db.session.add(
            SecurityEvent(user_id=user, kind="sign_in", created_at=utcnow() - timedelta(days=91))
        )
        db.session.commit()
        audit.record(account, "sign_in")
        db.session.commit()
        assert SecurityEvent.query.count() == 1


def test_unknown_event_kinds_are_rejected(app, user):
    with app.app_context(), pytest.raises(ValueError):
        audit.record(db.session.get(User, user), "made_up")
