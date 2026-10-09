"""Accounts lock after repeated failed sign-ins."""

from datetime import timedelta

from runnify.extensions import db, mail
from runnify.models import User, utcnow
from tests.conftest import PASSWORD

BAD = {"email": "runner@example.com", "password": "not the password"}
GOOD = {"email": "runner@example.com", "password": PASSWORD}


def _user(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id)


def test_five_failures_lock_the_account_and_notify_the_owner(app, client, user):
    with mail.record_messages() as outbox:
        for _ in range(5):
            client.post("/login", data=BAD)
    locked = _user(app, user)
    assert locked.failed_login_count == 5
    assert locked.locked_until > utcnow() + timedelta(minutes=14)
    assert len(outbox) == 1
    assert "sign-in paused" in outbox[0].subject
    assert outbox[0].recipients == ["runner@example.com"]


def test_correct_password_is_refused_while_locked(app, client, user):
    for _ in range(5):
        client.post("/login", data=BAD)
    response = client.post("/login", data=GOOD)
    assert response.status_code == 200
    assert b"combination didn" in response.data  # same message as a wrong password


def test_each_further_failure_doubles_the_lock(app, client, user):
    for _ in range(5):
        client.post("/login", data=BAD)
    with app.app_context():
        locked = db.session.get(User, user)
        locked.locked_until = utcnow() - timedelta(seconds=1)  # first lock expires
        db.session.commit()
    client.post("/login", data=BAD)
    assert _user(app, user).locked_until > utcnow() + timedelta(minutes=29)


def test_signing_in_after_the_lock_expires_clears_the_count(app, client, user):
    for _ in range(3):
        client.post("/login", data=BAD)
    assert client.post("/login", data=GOOD).status_code == 302
    cleared = _user(app, user)
    assert cleared.failed_login_count == 0
    assert cleared.locked_until is None
    assert cleared.last_login_at is not None


def test_failures_for_unknown_emails_lock_nothing(app, client, user):
    for _ in range(6):
        client.post("/login", data={"email": "ghost@example.com", "password": "x"})
    assert _user(app, user).failed_login_count == 0
