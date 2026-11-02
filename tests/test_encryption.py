"""Third-party credentials are encrypted at rest."""

import pytest
from cryptography.fernet import Fernet, InvalidToken
from flask_migrate import upgrade
from sqlalchemy import column as sa_column
from sqlalchemy import select, table, text

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db
from runnify.models import User
from runnify.security.crypto import FERNET_PREFIX


def _raw(column, user_id):
    """Read a column straight from the table, bypassing the model's decryption."""
    users = table("users", sa_column("id"), sa_column(column))
    return db.session.execute(select(users.c[column]).where(users.c.id == user_id)).scalar()


def test_tokens_are_stored_encrypted_and_read_back_plain(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.spotify_token = "access-123"
        account.spotify_refresh_token = "refresh-456"
        account.garmin_password = "garmin-secret"
        db.session.commit()
        for column, plain in [
            ("spotify_token", "access-123"),
            ("garmin_password", "garmin-secret"),
        ]:
            stored = _raw(column, user)
            assert stored.startswith("gAAAAA") and plain not in stored
        db.session.expire_all()
        reloaded = db.session.get(User, user)
        assert reloaded.spotify_token == "access-123"
        assert reloaded.garmin_password == "garmin-secret"


def test_legacy_plaintext_still_reads(app, user):
    with app.app_context():
        db.session.execute(
            text("UPDATE users SET spotify_token = 'legacy-plain' WHERE id = :id"), {"id": user}
        )
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(User, user).spotify_token == "legacy-plain"


def test_key_rotation_keeps_old_values_readable(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.spotify_token = "made-with-the-old-key"
        db.session.commit()
        new_key = Fernet.generate_key().decode()
        app.config["FERNET_KEYS"] = f"{new_key},{app.config['FERNET_KEY']}"
        db.session.expire_all()
        assert db.session.get(User, user).spotify_token == "made-with-the-old-key"


def test_values_under_a_removed_key_no_longer_load(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.totp_secret = "made-with-the-old-key"  # saved once, at set-up, never again
        db.session.commit()
        app.config["FERNET_KEYS"] = Fernet.generate_key().decode()  # the old key removed
        db.session.expire_all()
        with pytest.raises(InvalidToken):
            db.session.get(User, user)


def test_reencrypting_lets_the_old_key_go(app, user):
    old_key, new_key = app.config["FERNET_KEY"], Fernet.generate_key().decode()
    with app.app_context():
        db.session.get(User, user).totp_secret = "two-step"
        db.session.execute(  # from before encryption at rest
            text("UPDATE users SET spotify_token = 'legacy-plain' WHERE id = :id"), {"id": user}
        )
        db.session.commit()
        app.config["FERNET_KEYS"] = f"{new_key},{old_key}"
        db.session.get(User, user).garmin_tokens = "garmin"  # a sync saves these under the new key
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["secrets", "reencrypt"])
    assert result.exit_code == 0, result.output
    assert "Re-saved 2 values under the newest key." in result.output  # not the Garmin tokens
    app.config["FERNET_KEYS"] = new_key
    with app.app_context():
        account = db.session.get(User, user)
        assert (account.totp_secret, account.spotify_token, account.garmin_tokens) == (
            "two-step",
            "legacy-plain",
            "garmin",
        )
        assert _raw("spotify_token", user).startswith(FERNET_PREFIX)
    again = app.test_cli_runner().invoke(args=["secrets", "reencrypt"])
    assert "Re-saved 0 values under the newest key." in again.output


def test_reencrypting_names_values_no_key_can_read(app, user):
    stray = Fernet(Fernet.generate_key()).encrypt(b"lost").decode()  # its key is long gone
    with app.app_context():
        db.session.execute(
            text("UPDATE users SET totp_secret = :token WHERE id = :id"),
            {"token": stray, "id": user},
        )
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["secrets", "reencrypt"])
    assert result.exit_code == 1
    assert f"No configured key decrypts users.totp_secret for id {user}." in result.output
    with app.app_context():
        assert _raw("totp_secret", user) == stray  # left for the right key to read


def test_migration_encrypts_existing_plaintext_tokens(tmp_path):
    class MigratedConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"

    app = create_app(MigratedConfig)
    with app.app_context():
        upgrade(revision="0003")
        db.session.execute(
            text(
                "INSERT INTO users (name, email, password_hash, created_at, session_token, spotify_token) "
                "VALUES ('u', 'u@example.com', 'x', CURRENT_TIMESTAMP, 'tok', 'plain-access')"
            )
        )
        db.session.commit()
        upgrade()  # through 0004 (the data migration) to the latest revision
        stored = db.session.execute(text("SELECT spotify_token FROM users")).scalar()
        assert stored.startswith("gAAAAA")
        assert db.session.execute(text("SELECT id FROM users")).scalar() == 1
        db.session.expire_all()
        assert db.session.get(User, 1).spotify_token == "plain-access"
        db.session.remove()
        db.engine.dispose()
