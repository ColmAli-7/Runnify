"""The security activity log."""

from datetime import timedelta

import pytest
from flask_migrate import upgrade
from sqlalchemy import text

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db
from runnify.models import SecurityEvent, User, utcnow
from runnify.security import audit
from tests.conftest import PASSWORD

LOGIN = {"email": "runner@example.com", "password": PASSWORD}
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"


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


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        (CHROME, "Chrome on Windows"),
        (
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Firefox on Linux",
        ),
        ("curl/8.0", None),
        ("", None),
        (None, None),
    ],
)
def test_browsers_are_described_briefly(agent, expected):
    assert audit.describe_browser(agent) == expected


def test_sign_ins_and_failures_are_logged(app, client, user):
    client.post("/login", data={**LOGIN, "password": "wrong"})
    client.post(
        "/login",
        data=LOGIN,
        environ_base={"REMOTE_ADDR": "198.51.100.23"},
        headers={"User-Agent": CHROME},
    )
    assert _kinds(app, user) == ["sign_in_failed", "sign_in"]
    with app.app_context():
        event = SecurityEvent.query.filter_by(kind="sign_in").one()
        assert event.ip_prefix == "198.51.100.0"
        assert event.user_agent == "Chrome on Windows"  # never the user agent itself


def test_migration_keeps_only_a_short_description(tmp_path):
    class MigratedConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"

    app = create_app(MigratedConfig)
    with app.app_context():
        upgrade(revision="0019")
        db.session.execute(
            text(
                "INSERT INTO users (id, name, email, password_hash, created_at, session_token) "
                "VALUES (1, 'a', 'a@example.com', 'x', CURRENT_TIMESTAMP, 'a')"
            )
        )
        db.session.execute(
            text(
                "INSERT INTO security_events (user_id, kind, user_agent, created_at) VALUES "
                "(1, 'sign_in', :chrome, CURRENT_TIMESTAMP), "
                "(1, 'sign_in', 'curl/8.0', CURRENT_TIMESTAMP), "
                "(1, 'sign_in', NULL, CURRENT_TIMESTAMP)"
            ),
            {"chrome": CHROME},
        )
        db.session.commit()
        upgrade()
        stored = db.session.execute(text("SELECT user_agent FROM security_events ORDER BY id"))
        assert stored.scalars().all() == ["Chrome on Windows", None, None]
        db.session.remove()
        db.engine.dispose()


def test_lockout_is_logged(app, client, user):
    for _ in range(5):
        client.post("/login", data={**LOGIN, "password": "wrong"})
    assert _kinds(app, user)[-2:] == ["sign_in_failed", "account_locked"]


def test_password_change_and_revocation_are_logged(app, auth_client, user):
    new = "a completely new passphrase"
    auth_client.post(
        "/settings", data={"password": PASSWORD, "new_password": new, "confirm_password": new}
    )
    auth_client.post("/settings", data={"action": "sign_out_everywhere"})
    assert _kinds(app, user) == ["password_changed", "sessions_revoked"]


def test_settings_show_recent_activity(app, auth_client, user):
    with app.app_context():
        audit.record(db.session.get(User, user), "password_changed")  # no request, no browser
        db.session.add(SecurityEvent(user_id=user, kind="sign_in", user_agent="Chrome on Windows"))
        db.session.commit()
    page = auth_client.get("/settings").data
    assert b"Password changed" in page
    assert b"Chrome on Windows" in page and b"Unknown device" in page


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
