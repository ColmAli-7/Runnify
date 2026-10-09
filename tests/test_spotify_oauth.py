"""Spotify OAuth: state checks, token storage and no shared token cache."""

import pathlib
from urllib.parse import parse_qs, urlsplit

import pytest

from runnify.extensions import db
from runnify.models import User
from runnify.services import spotify as spotify_service

TOKEN_INFO = {"access_token": "acc", "refresh_token": "ref", "expires_at": 4_102_444_800}


@pytest.fixture
def exchanges(monkeypatch):
    """Replace the network call that swaps a code for tokens."""
    calls = []

    def fake_exchange(code):
        calls.append(code)
        return dict(TOKEN_INFO)

    monkeypatch.setattr(spotify_service, "exchange_code", fake_exchange)
    return calls


def _start(client):
    response = client.get("/spotify/login")
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["Location"]).query)
    return query["state"][0]


def test_login_redirects_to_spotify_with_a_state(auth_client):
    state = _start(auth_client)
    assert len(state) >= 24


def test_callback_with_matching_state_stores_tokens(app, auth_client, user, exchanges):
    state = _start(auth_client)
    response = auth_client.get(f"/spotify/callback?code=abc&state={state}")
    assert response.headers["Location"] == "/connections"
    assert exchanges == ["abc"]
    with app.app_context():
        account = db.session.get(User, user)
        assert (account.spotify_token, account.spotify_refresh_token) == ("acc", "ref")


@pytest.mark.parametrize("query", ["code=abc&state=forged", "code=abc", "state=&code=abc"])
def test_callback_with_wrong_or_missing_state_is_ignored(app, auth_client, user, exchanges, query):
    _start(auth_client)
    auth_client.get(f"/spotify/callback?{query}")
    assert exchanges == []
    with app.app_context():
        assert db.session.get(User, user).spotify_token is None


def test_state_is_single_use(auth_client, exchanges):
    state = _start(auth_client)
    auth_client.get(f"/spotify/callback?code=abc&state={state}")
    auth_client.get(f"/spotify/callback?code=again&state={state}")
    assert exchanges == ["abc"]


def test_user_cancelling_on_spotify_is_handled(auth_client, exchanges):
    state = _start(auth_client)
    response = auth_client.get(
        f"/spotify/callback?error=access_denied&state={state}", follow_redirects=True
    )
    assert b"wasn" in response.data and exchanges == []


def test_missing_code_never_reaches_spotipy(auth_client, exchanges):
    state = _start(auth_client)
    assert auth_client.get(f"/spotify/callback?state={state}").status_code == 400
    assert exchanges == []


def test_oauth_helper_never_writes_a_shared_cache_file(app, tmp_path):
    with app.app_context():
        helper = spotify_service.oauth()
        helper.cache_handler.save_token_to_cache(TOKEN_INFO)
    assert not any(pathlib.Path(".").glob(".cache*"))
