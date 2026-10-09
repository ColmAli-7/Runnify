"""Shared pytest fixtures: an isolated app, a client and a signed-in user."""

import pytest
from werkzeug.security import generate_password_hash

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db as _db
from runnify.models import User


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A fresh application with an in-memory database, run from a temp directory."""
    monkeypatch.chdir(tmp_path)  # files the app writes (e.g. fit_files/) land in tmp
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """A test client for ``app``."""
    return app.test_client()


@pytest.fixture
def user(app):
    """A saved user; returns its id."""
    with app.app_context():
        user = User(
            name="Test Runner",
            email="runner@example.com",
            password_hash=generate_password_hash("correct horse 1!"),
        )
        _db.session.add(user)
        _db.session.commit()
        return user.id


@pytest.fixture
def auth_client(client, user):
    """A test client whose session is signed in as ``user``."""
    with client.session_transaction() as session:
        session["_user_id"] = str(user)
        session["_fresh"] = True
    return client
