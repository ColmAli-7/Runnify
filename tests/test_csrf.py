"""Every state-changing form must carry a valid CSRF token."""

import pytest

from runnify import create_app
from runnify.config import TestConfig


class CSRFConfig(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def csrf_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(CSRFConfig)
    from runnify.extensions import db

    with app.app_context():
        db.create_all()
    return app.test_client()


@pytest.mark.parametrize("path", ["/login", "/register", "/forgot"])
def test_posts_without_a_token_are_rejected(csrf_client, path):
    response = csrf_client.post(path, data={"email": "a@example.com", "password": "x"})
    assert response.status_code == 303
    assert response.headers["Location"] == path


@pytest.mark.parametrize("path", ["/login", "/register", "/forgot"])
def test_forms_render_a_token(csrf_client, path):
    assert b'name="csrf_token"' in csrf_client.get(path).data
