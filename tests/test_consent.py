"""Consent: recorded at sign-up, and asked again of accounts without current consent."""

import pytest

from runnify.extensions import db
from runnify.models import User

REGISTRATION = {
    "name": "New Runner",
    "email": "new@example.com",
    "password": "correct horse battery staple",
}


def test_registration_needs_both_agreements(app, client):
    for missing in ("accept_terms", "data_consent"):
        form = {**REGISTRATION, "accept_terms": "y", "data_consent": "y"}
        del form[missing]
        assert client.post("/register", data=form).status_code == 200  # form shown again
    with app.app_context():
        assert User.query.count() == 0


def test_registration_records_consent(app, client):
    client.post("/register", data={**REGISTRATION, "accept_terms": "y", "data_consent": "y"})
    with app.app_context():
        user = User.query.one()
        assert user.terms_accepted_at and user.data_consent_at
        assert user.policy_version == app.config["POLICY_VERSION"]


@pytest.fixture
def unconsented(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.data_consent_at = account.terms_accepted_at = account.policy_version = None
        db.session.commit()
    return user


def test_accounts_without_consent_are_asked_first(auth_client, unconsented):
    response = auth_client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/consent?next=/dashboard")


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/cookies", "/consent", "/manage"])
def test_policies_and_account_exits_stay_reachable(auth_client, unconsented, path):
    assert auth_client.get(path).status_code == 200


def test_agreeing_continues_where_the_user_was_going(app, auth_client, unconsented):
    response = auth_client.post(
        "/consent?next=/friends", data={"accept_terms": "y", "data_consent": "y"}
    )
    assert response.headers["Location"] == "/friends"
    assert auth_client.get("/dashboard").status_code == 200


def test_a_new_policy_version_asks_again(app, auth_client, user):
    app.config["POLICY_VERSION"] = "2027-01"
    assert auth_client.get("/dashboard").headers["Location"].startswith("/consent")


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/cookies"])
def test_legal_pages_are_public(client, path):
    page = client.get(path)
    assert page.status_code == 200
    assert b"Last updated" in page.data
