"""Argon2id hashing, legacy hash upgrades and timing-safe failures."""

from werkzeug.security import generate_password_hash

from runnify.extensions import db
from runnify.models import User
from runnify.security.passwords import hash_password, verify_password
from tests.conftest import PASSWORD


def test_argon2id_round_trip():
    stored = hash_password("a long passphrase")
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, "a long passphrase") == (True, False)
    assert verify_password(stored, "wrong") == (False, False)


def test_legacy_werkzeug_hashes_verify_and_ask_for_rehash():
    legacy = generate_password_hash("old password")
    assert verify_password(legacy, "old password") == (True, True)
    assert verify_password(legacy, "nope") == (False, False)


def test_missing_account_and_garbage_hashes_fail_safely():
    assert verify_password(None, "anything") == (False, False)
    assert verify_password("not-a-hash", "anything") == (False, False)


def test_login_upgrades_a_legacy_hash(app, client):
    with app.app_context():
        user = User(
            name="Old", email="old@example.com", password_hash=generate_password_hash(PASSWORD)
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post("/login", data={"email": "old@example.com", "password": PASSWORD})
    assert response.status_code == 302

    with app.app_context():
        assert db.session.get(User, user_id).password_hash.startswith("$argon2id$")
