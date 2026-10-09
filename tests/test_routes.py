"""Smoke tests: public pages render, protected pages require a session."""

import pytest

PUBLIC_PAGES = ["/", "/login", "/register", "/forgot"]
PROTECTED_PAGES = [
    "/dashboard",
    "/runs",
    "/runs/1",
    "/insights",
    "/friends",
    "/friends/search",
    "/settings",
    "/playlists",
    "/connections",
    "/spotify/login",
    "/import",
]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_unknown_page_returns_custom_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_protected_pages_redirect_anonymous_users_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


@pytest.mark.parametrize("path", ["/dashboard", "/runs", "/insights", "/friends", "/settings"])
def test_signed_in_pages_render(auth_client, path):
    assert auth_client.get(path).status_code == 200
