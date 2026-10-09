"""Two-step verification: set-up, sign-in, recovery codes and brute-force protection."""

import re

import pyotp
import pytest

from runnify.extensions import db, mail
from runnify.models import User
from runnify.security.two_factor import accept_code
from tests.conftest import PASSWORD, sign_in_as

LOGIN = {"email": "runner@example.com", "password": PASSWORD}


def _setup_secret(client):
    client.get("/settings/two-factor")
    with client.session_transaction() as session:
        return session["two_factor_setup_secret"]


def _enable(client):
    """Turn on 2FA for the signed-in user; returns (secret, recovery codes)."""
    secret = _setup_secret(client)
    page = client.post(
        "/settings/two-factor", data={"code": pyotp.TOTP(secret).now(), "password": PASSWORD}
    )
    codes = re.findall(r"<code>([0-9a-f]{5}-[0-9a-f]{5})</code>", page.get_data(as_text=True))
    return secret, codes


@pytest.fixture
def enabled(app, auth_client, user):
    secret, codes = _enable(auth_client)
    auth_client.post("/logout")
    with app.app_context():  # let the set-up code's time step pass, so it can't block the next code
        db.session.get(User, user).totp_last_step = None
        db.session.commit()
    return secret, codes


def test_setup_page_shows_a_qr_code_and_key(auth_client):
    page = auth_client.get("/settings/two-factor").get_data(as_text=True)
    assert "<svg" in page and 'class="segno"' in page
    assert re.search(r"<code>([A-Z2-7]{4} ){7}[A-Z2-7]{4}</code>", page)


def test_enabling_needs_the_password_and_a_working_code(app, auth_client, user):
    secret = _setup_secret(auth_client)
    wrong_password = auth_client.post(
        "/settings/two-factor", data={"code": pyotp.TOTP(secret).now(), "password": "nope"}
    )
    assert b"current password is incorrect" in wrong_password.data
    wrong_code = auth_client.post(
        "/settings/two-factor", data={"code": "000000", "password": PASSWORD}
    )
    assert b"code didn" in wrong_code.data
    with app.app_context():
        assert not db.session.get(User, user).two_factor_enabled


def test_enabling_shows_ten_recovery_codes_signs_out_others_and_notifies(app, auth_client, user):
    other_device = app.test_client()
    sign_in_as(other_device, user)
    with mail.record_messages() as outbox:
        _, codes = _enable(auth_client)
    assert len(codes) == 10 and len(set(codes)) == 10
    assert outbox[0].subject == "Two-step verification turned on for Runnify"
    assert other_device.get("/dashboard").status_code == 302
    with app.app_context():
        assert db.session.get(User, user).two_factor_enabled


def test_sign_in_asks_for_a_code_after_the_password(client, enabled):
    secret, _ = enabled
    first = client.post("/login?next=/friends", data=LOGIN)
    assert first.headers["Location"] == "/login/verify"
    assert client.get("/dashboard").status_code == 302  # not signed in yet
    done = client.post("/login/verify", data={"code": pyotp.TOTP(secret).now()})
    assert done.headers["Location"] == "/friends"
    assert client.get("/dashboard").status_code == 200


def test_a_code_cannot_be_replayed(app, client, enabled, user):
    secret, _ = enabled
    code = pyotp.TOTP(secret).now()
    client.post("/login", data=LOGIN)
    client.post("/login/verify", data={"code": code})
    client.post("/logout")
    client.post("/login", data=LOGIN)
    replay = client.post("/login/verify", data={"code": code})
    assert b"code didn" in replay.data


def test_recovery_codes_work_once(client, enabled):
    _, codes = enabled
    client.post("/login", data=LOGIN)
    used = client.post("/login/verify", data={"code": codes[0].upper()}, follow_redirects=True)
    assert b"9 left" in used.data
    client.post("/logout")
    client.post("/login", data=LOGIN)
    again = client.post("/login/verify", data={"code": codes[0]})
    assert b"code didn" in again.data


def test_wrong_codes_count_towards_lockout(app, client, enabled, user):
    secret, _ = enabled
    client.post("/login", data=LOGIN)
    for _ in range(5):
        client.post("/login/verify", data={"code": "000000"})
    locked = client.post("/login/verify", data={"code": pyotp.TOTP(secret).now()})
    assert b"code didn" in locked.data
    with app.app_context():
        assert db.session.get(User, user).locked_until is not None


def test_the_verify_step_needs_a_fresh_password_step(client):
    response = client.get("/login/verify")
    assert response.headers["Location"] == "/login"


def test_disabling_needs_password_and_code(app, auth_client, user):
    _, codes = _enable(auth_client)
    auth_client.post("/settings/two-factor/disable", data={"password": PASSWORD, "code": "000000"})
    with app.app_context():
        assert db.session.get(User, user).two_factor_enabled
    auth_client.post("/settings/two-factor/disable", data={"password": PASSWORD, "code": codes[1]})
    with app.app_context():
        assert not db.session.get(User, user).two_factor_enabled


def test_new_recovery_codes_replace_the_old_ones(app, auth_client, user):
    _, old_codes = _enable(auth_client)
    page = auth_client.post("/settings/two-factor/recovery-codes", data={"password": PASSWORD})
    new_codes = re.findall(r"<code>([0-9a-f]{5}-[0-9a-f]{5})</code>", page.get_data(as_text=True))
    assert len(new_codes) == 10 and not set(new_codes) & set(old_codes)


def test_codes_use_the_current_utc_time_step(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.totp_secret = pyotp.random_base32()
        assert accept_code(account, pyotp.TOTP(account.totp_secret).now())
