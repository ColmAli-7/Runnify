"""Password reset: no enumeration, single-use links, sessions revoked."""

import re

from runnify.extensions import db, mail
from runnify.models import User
from runnify.security.passwords import verify_password
from runnify.security.tokens import make_reset_token
from tests.conftest import PASSWORD, sign_in_as

NEW_PASSWORD = "a fresh and lengthy passphrase"


def _request_link(client, email="runner@example.com"):
    with mail.record_messages() as outbox:
        response = client.post("/forgot", data={"email": email}, follow_redirects=True)
    return response, outbox


def _link_path(message):
    return re.search(r"http://localhost(/reset/\S+)", message.body).group(1)


def test_response_is_identical_for_unknown_and_known_emails(client, user):
    known, sent = _request_link(client)
    unknown, not_sent = _request_link(client, "ghost@example.com")
    assert len(sent) == 1 and len(not_sent) == 0
    for response, email in [(known, b"runner@example.com"), (unknown, b"ghost@example.com")]:
        assert b"If an account exists for " + email in response.data


def test_full_reset_journey(app, client, user):
    other_device = app.test_client()
    sign_in_as(other_device, user)
    _, outbox = _request_link(client)
    link = _link_path(outbox[0])

    landing = client.get(link)
    assert (
        landing.status_code == 302 and landing.headers["Location"] == "/reset"
    )  # token leaves the URL
    assert client.get("/reset").status_code == 200

    with mail.record_messages() as notices:
        done = client.post("/reset", data={"password": NEW_PASSWORD, "confirm": NEW_PASSWORD})
    assert done.headers["Location"] == "/login"
    assert notices[0].subject == "Your Runnify password was changed"

    with app.app_context():
        account = db.session.get(User, user)
        assert verify_password(account.password_hash, NEW_PASSWORD)[0]
        assert not verify_password(account.password_hash, PASSWORD)[0]
    assert other_device.get("/dashboard").status_code == 302  # signed out everywhere

    reused = client.get(link)  # single use
    assert reused.headers["Location"] == "/forgot"


def test_weak_and_mismatched_passwords_are_refused(client, user):
    _, outbox = _request_link(client)
    client.get(_link_path(outbox[0]))
    weak = client.post("/reset", data={"password": "Password2026!", "confirm": "Password2026!"})
    assert b"too common" in weak.data
    mismatch = client.post("/reset", data={"password": NEW_PASSWORD, "confirm": "something else"})
    assert b"match" in mismatch.data


def test_reset_lifts_a_lockout(app, client, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.failed_login_count = 9
        from runnify.models import utcnow

        account.locked_until = utcnow().replace(year=2099)
        db.session.commit()
    _, outbox = _request_link(client)
    client.get(_link_path(outbox[0]))
    client.post("/reset", data={"password": NEW_PASSWORD, "confirm": NEW_PASSWORD})
    response = client.post("/login", data={"email": "runner@example.com", "password": NEW_PASSWORD})
    assert response.headers["Location"] == "/dashboard"


def test_expired_and_tampered_tokens_are_rejected(app, client, user):
    with app.test_request_context():
        token = make_reset_token(db.session.get(User, user))
    assert client.get(f"/reset/{token}x").headers["Location"] == "/forgot"
    app.config["PASSWORD_RESET_MAX_AGE"] = -1
    assert client.get(f"/reset/{token}").headers["Location"] == "/forgot"


def test_choosing_a_password_without_a_token_is_refused(client):
    assert client.get("/reset").headers["Location"] == "/forgot"
