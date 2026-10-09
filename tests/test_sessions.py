"""Session tokens: changing the password signs out every other device."""

from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db
from runnify.models import User
from tests.conftest import PASSWORD, sign_in_as

NEW_PASSWORD = "an entirely new passphrase"


def test_cookie_id_includes_the_session_token(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        assert account.get_id() == f"{account.id}:{account.session_token}"


def test_old_style_and_forged_session_ids_are_rejected(app, client, user):
    for session_id in [str(user), f"{user}:wrong-token", "abc:def", ""]:
        with client.session_transaction() as session:
            session["_user_id"] = session_id
        assert client.get("/dashboard").status_code == 302


def test_password_change_signs_out_other_devices_but_not_this_one(app, user):
    this_device, other_device = app.test_client(), app.test_client()
    sign_in_as(this_device, user)
    sign_in_as(other_device, user)

    this_device.post(
        "/manage",
        data={"password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )

    assert this_device.get("/dashboard").status_code == 200
    assert other_device.get("/dashboard").status_code == 302


def test_sign_out_everywhere(app, user):
    this_device, other_device = app.test_client(), app.test_client()
    sign_in_as(this_device, user)
    sign_in_as(other_device, user)

    this_device.post("/manage", data={"action": "sign_out_everywhere"})

    assert this_device.get("/dashboard").status_code == 200
    assert other_device.get("/dashboard").status_code == 302


def test_migration_gives_existing_users_unique_tokens(tmp_path):
    class MigratedConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"

    app = create_app(MigratedConfig)
    with app.app_context():
        upgrade(revision="0002")
        for n in range(3):
            db.session.execute(
                text(
                    "INSERT INTO users (name, email, password_hash, created_at) VALUES (:n, :e, 'x', CURRENT_TIMESTAMP)"
                ),
                {"n": f"u{n}", "e": f"u{n}@example.com"},
            )
        db.session.commit()
        upgrade(revision="0003")
        tokens = [row[0] for row in db.session.execute(text("SELECT session_token FROM users"))]
        assert len(set(tokens)) == 3 and all(len(t) >= 40 for t in tokens)
        downgrade(revision="0002")
        db.session.remove()
        db.engine.dispose()
