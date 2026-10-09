"""Shared pytest fixtures: an isolated app, a client and a signed-in user."""

import pytest

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db as _db
from runnify.models import User
from runnify.security.passwords import hash_password

PASSWORD = "correct horse battery staple"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A fresh application with an in-memory database, run from a temp directory."""
    monkeypatch.chdir(tmp_path)  # files the app writes (e.g. fit_files/) land in tmp
    app = create_app(TestConfig)
    app.config["FIT_STORAGE_DIR"] = str(tmp_path / "fit_files")
    app.config["UPLOAD_TMP_DIR"] = str(tmp_path / "uploads")
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
            password_hash=hash_password(PASSWORD),
        )
        user.record_consent()
        _db.session.add(user)
        _db.session.commit()
        return user.id


@pytest.fixture
def auth_client(client, user):
    """A test client whose session is signed in as ``user``."""
    sign_in_as(client, user)
    return client


def sign_in_as(client, user_id):
    """Put a valid session for ``user_id`` into ``client``'s cookie jar."""
    with client.application.app_context():
        session_id = _db.session.get(User, user_id).get_id()
    with client.session_transaction() as session:
        session["_user_id"] = session_id
        session["_fresh"] = True
