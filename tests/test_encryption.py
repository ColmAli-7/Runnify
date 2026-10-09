"""Third-party credentials are encrypted at rest."""

from cryptography.fernet import Fernet
from flask_migrate import upgrade
from sqlalchemy import column as sa_column
from sqlalchemy import select, table, text

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db
from runnify.models import User


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
