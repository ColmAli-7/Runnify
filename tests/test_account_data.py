"""Data export and account deletion."""

import json
import pathlib
from datetime import datetime

from runnify.extensions import db, mail
from runnify.models import (
    FriendRequest,
    Run,
    RunSongAnalysis,
    SecurityEvent,
    Song,
    User,
    UserSongHistory,
)
from runnify.security.passwords import hash_password
from tests.conftest import PASSWORD


def _seed(app, user_id):
    """One run with one scored song play, a friend request and a stored FIT file."""
    with app.app_context():
        other = User(name="Friend", email="friend@example.com", password_hash=hash_password("x"))
        db.session.add(other)
        run = Run(
            user_id=user_id,
            activity_id="42",
            date_time=datetime(2026, 10, 1, 7),
            distance=5000,
            duration=1500,
        )
        db.session.add_all([run, Song(id="trk", name="Song", artist="Artist")])
        db.session.flush()
        play = UserSongHistory(
            user_id=user_id,
            song_id="trk",
            run_id=run.id,
            played_at=datetime(2026, 10, 1, 7, 1),
            time_played=180,
        )
        db.session.add(play)
        db.session.flush()
        db.session.add_all(
            [
                RunSongAnalysis(
                    run_id=run.id, user_song_id=play.id, performance_score=61.5, user_id=user_id
                ),
                FriendRequest(sender_id=other.id, receiver_id=user_id),
            ]
        )
        account = db.session.get(User, user_id)
        account.spotify_token, account.spotify_refresh_token = "secret-access", "secret-refresh"
        fit_dir = pathlib.Path(app.config["FIT_STORAGE_DIR"]) / str(user_id)
        fit_dir.mkdir(parents=True)
        (fit_dir / "42.fit").write_bytes(b"FIT")
        run.fit_file_path = str(fit_dir / "42.fit")
        db.session.commit()
        return other.id


def test_export_contains_the_data_but_no_secrets(app, auth_client, user):
    _seed(app, user)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    assert response.headers["Content-Disposition"] == 'attachment; filename="runnify-data.json"'
    data = json.loads(response.data)
    assert data["account"]["email"] == "runner@example.com"
    assert data["runs"][0]["garmin_activity_id"] == "42"
    assert data["song_plays_during_runs"][0]["track"] == "Song"
    assert data["song_scores"][0]["score"] == 61.5
    text = response.get_data(as_text=True)
    for secret in ("secret-access", "secret-refresh", "argon2", "password_hash", "session_token"):
        assert secret not in text


def test_export_needs_the_password(auth_client):
    response = auth_client.post("/settings/export", data={"password": "wrong"})
    assert response.status_code == 302


def test_deleting_removes_everything_personal(app, auth_client, user):
    other = _seed(app, user)
    with mail.record_messages() as outbox:
        response = auth_client.post("/settings/delete", data={"password": PASSWORD, "confirm": "y"})
    assert response.headers["Location"] == "/"
    assert outbox[0].subject == "Your Runnify account was deleted"
    with app.app_context():
        assert db.session.get(User, user) is None
        for model in (Run, UserSongHistory, RunSongAnalysis, FriendRequest, SecurityEvent):
            assert model.query.count() == 0, model.__name__
        assert db.session.get(User, other) is not None  # the friend's account is untouched
        assert db.session.get(Song, "trk") is not None  # the shared catalogue is kept
    assert not (pathlib.Path(app.config["FIT_STORAGE_DIR"]) / str(user)).exists()
    assert auth_client.get("/dashboard").status_code == 302  # signed out


def test_deleting_needs_password_and_confirmation(app, auth_client, user):
    auth_client.post("/settings/delete", data={"password": PASSWORD})
    auth_client.post("/settings/delete", data={"password": "wrong", "confirm": "y"})
    with app.app_context():
        assert db.session.get(User, user) is not None
