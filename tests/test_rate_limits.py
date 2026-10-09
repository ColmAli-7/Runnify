"""Brute-force-able endpoints are rate limited."""

import pytest

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db, limiter


class LimitedConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RATE_LIMIT_LOGIN = "3 per minute"
    RATE_LIMIT_REGISTER = "2 per hour"


@pytest.fixture
def limited_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(LimitedConfig)
    with app.app_context():
        db.create_all()
    limiter.reset()  # counters live in process memory; start every test from zero
    return app.test_client()


def test_login_attempts_are_limited_per_ip(limited_client):
    attempt = {"email": "nobody@example.com", "password": "wrong"}
    statuses = [limited_client.post("/login", data=attempt).status_code for _ in range(4)]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
    assert b"Too many attempts" in limited_client.post("/login", data=attempt).data


def test_viewing_the_login_page_is_not_limited(limited_client):
    assert all(limited_client.get("/login").status_code == 200 for _ in range(10))


def test_registration_is_limited(limited_client):
    form = {"name": "A", "email": "a@example.com", "password": "short"}
    statuses = [limited_client.post("/register", data=form).status_code for _ in range(3)]
    assert statuses[-1] == 429
