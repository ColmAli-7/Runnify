"""Sign-in, registration and redirects."""

import pytest

from tests.conftest import PASSWORD


def test_login_with_valid_credentials_goes_to_the_dashboard(client, user):
    response = client.post("/login", data={"email": " Runner@Example.com ", "password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"


def test_failed_login_message_does_not_reveal_whether_the_account_exists(client, user):
    wrong_password = client.post("/login", data={"email": "runner@example.com", "password": "nope"})
    no_account = client.post("/login", data={"email": "ghost@example.com", "password": "nope"})
    assert b"combination didn" in wrong_password.data
    assert b"combination didn" in no_account.data


def test_login_follows_a_local_next_path(client, user):
    response = client.post(
        "/login?next=/music-insights", data={"email": "runner@example.com", "password": PASSWORD}
    )
    assert response.headers["Location"] == "/music-insights"


@pytest.mark.parametrize(
    "target", ["https://evil.example", "//evil.example", r"/\evil.example", "javascript:alert(1)"]
)
def test_login_ignores_off_site_next_targets(client, user, target):
    response = client.post(
        "/login",
        query_string={"next": target},
        data={"email": "runner@example.com", "password": PASSWORD},
    )
    assert response.headers["Location"] == "/dashboard"


def test_signed_in_users_skip_the_login_page(auth_client):
    assert auth_client.get("/login").headers["Location"] == "/dashboard"


def test_registration_rejects_invalid_email(client):
    response = client.post(
        "/register",
        data={
            "accept_terms": "y",
            "data_consent": "y",
            "name": "A",
            "email": "not-an-email",
            "password": "correct horse battery staple",
        },
    )
    assert b"valid email" in response.data


def test_registration_rejects_duplicate_email(client, user):
    response = client.post(
        "/register",
        data={
            "accept_terms": "y",
            "data_consent": "y",
            "name": "B",
            "email": "RUNNER@example.com",
            "password": "another fine passphrase",
        },
    )
    assert b"already registered" in response.data


def test_password_change_requires_the_current_password(auth_client):
    response = auth_client.post(
        "/manage",
        data={
            "password": "wrong",
            "new_password": "a brand new passphrase",
            "confirm_password": "a brand new passphrase",
        },
        follow_redirects=True,
    )
    assert b"current password is incorrect" in response.data


def test_password_change_with_mismatched_confirmation(auth_client):
    response = auth_client.post(
        "/manage",
        data={
            "password": PASSWORD,
            "new_password": "a brand new passphrase",
            "confirm_password": "different",
        },
        follow_redirects=True,
    )
    assert b"don&#39;t match" in response.data or b"don't match" in response.data
