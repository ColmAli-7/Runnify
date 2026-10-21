"""Data export and account deletion."""

import json
import pathlib
from datetime import datetime, timedelta

from runnify.extensions import db, mail
from runnify.models import (
    FriendRequest,
    Playlist,
    PlaylistTrack,
    Run,
    RunLap,
    RunSongAnalysis,
    RunStream,
    SecurityEvent,
    Song,
    User,
    UserSongHistory,
)
from runnify.security.passwords import hash_password
from runnify.services.account import to_json
from runnify.services.fit import Series, WatchLap
from runnify.services.streams import save_stream
from tests.conftest import PASSWORD


def _seed(app, user_id):
    """Two runs (one recorded, with a lap and a scored play), a friend request and a FIT file."""
    with app.app_context():
        other = User(name="Friend", email="friend@example.com", password_hash=hash_password("x"))
        db.session.add(other)
        run = Run(
            user_id=user_id,
            activity_id="42",
            date_time=datetime(2026, 10, 1, 7),
            distance=5000,
            duration=1500,
            run_type="easy",
        )
        unrecorded = Run(
            user_id=user_id, activity_id="43", date_time=datetime(2026, 10, 2, 7), distance=3000
        )
        db.session.add_all([run, unrecorded, Song(id="trk", name="Song", artist="Artist")])
        db.session.flush()
        db.session.add(
            RunLap(
                run_id=run.id,
                position=0,
                start_second=0,
                end_second=1500,
                kind="steady",
                distance=5000,
            )
        )
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
        save_stream(
            run,
            Series(
                # smart recording: a sample every two seconds, stopped at the last
                timestamps=[run.date_time + timedelta(seconds=s) for s in (0, 2, 4)],
                heart_rates=[140, 141, None],
                paces=[300.0, 299.5, None],
                cadences=[170, 172, None],
                distances=[0.0, 6.6, 13.2],
                laps=[WatchLap(0, 4, "active", "manual")],
            ),
        )
        db.session.commit()
        return other.id


def test_export_contains_the_data_but_no_secrets(app, auth_client, user):
    _seed(app, user)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    assert response.headers["Content-Disposition"] == 'attachment; filename="runnify-data.json"'
    data = json.loads(response.data)
    assert data["account"]["email"] == "runner@example.com"
    assert data["runs"][0]["garmin_activity_id"] == "42"
    assert data["runs"][0]["run_type"] == "easy"
    assert data["runs"][0]["laps"] == [
        {"kind": "steady", "start_s": 0, "end_s": 1500, "distance_m": 5000}
    ]
    assert data["song_plays_during_runs"][0]["track"] == "Song"
    assert data["song_scores"][0]["score"] == 61.5
    text = response.get_data(as_text=True)
    for secret in ("secret-access", "secret-refresh", "argon2", "password_hash", "session_token"):
        assert secret not in text


def test_export_gives_each_runs_recording_as_stored(app, auth_client, user):
    _seed(app, user)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    recorded, unrecorded = json.loads(response.data)["runs"]
    assert recorded["samples"] == {
        "started_at": "2026-10-01T07:00:00Z",
        "seconds": [0, 2, 4],  # as the watch recorded them, not spread to one a second
        "pace_s_per_km": [300.0, 299.5, None],
        "heart_rate_bpm": [140, 141, None],
        "cadence_steps_per_min": [170, 172, None],
        "distance_m": [0, 7, 13],
    }
    assert recorded["watch_laps"] == [
        {"start_s": 0, "end_s": 4, "intensity": "active", "trigger": "manual", "workout_step": None}
    ]
    assert unrecorded["garmin_activity_id"] == "43"
    assert "samples" not in unrecorded and "watch_laps" not in unrecorded
    assert '"seconds": [0,2,4],' in response.get_data(as_text=True)  # a channel to a line


def test_to_json_puts_each_list_of_plain_values_on_one_line():
    value = {"runs": [{"seconds": [0, 1], "laps": [], "workout": None}], "friends": ["Ann"]}
    text = to_json(value)
    assert json.loads(text) == value
    assert text == (
        "{\n"
        '  "runs": [\n'
        "    {\n"
        '      "seconds": [0,1],\n'
        '      "laps": [],\n'
        '      "workout": null\n'
        "    }\n"
        "  ],\n"
        '  "friends": ["Ann"]\n'
        "}"
    )


def test_export_needs_the_password(auth_client):
    response = auth_client.post("/settings/export", data={"password": "wrong"})
    assert response.status_code == 302


def test_deleting_removes_everything_personal(app, auth_client, user):
    other = _seed(app, user)
    with app.app_context():  # a song the friend keeps in a playlist
        playlist = Playlist(user_id=other, name="Theirs", session="easy", target_minutes=30)
        db.session.add_all([playlist, Song(id="theirs", name="Kept", artist="Artist")])
        db.session.flush()
        db.session.add(
            PlaylistTrack(playlist_id=playlist.id, position=0, song_id="theirs", seconds=200)
        )
        db.session.commit()
    with mail.record_messages() as outbox:
        response = auth_client.post("/settings/delete", data={"password": PASSWORD, "confirm": "y"})
    assert response.headers["Location"] == "/"
    assert outbox[0].subject == "Your Runnify account was deleted"
    with app.app_context():
        assert db.session.get(User, user) is None
        for model in (
            Run,
            RunLap,
            RunStream,
            UserSongHistory,
            RunSongAnalysis,
            FriendRequest,
            SecurityEvent,
        ):
            assert model.query.count() == 0, model.__name__
        assert db.session.get(User, other) is not None  # the friend's account is untouched
        assert db.session.get(Song, "trk") is None  # nobody else's runs used it
        assert db.session.get(Song, "theirs") is not None  # still in the friend's playlist
    assert not (pathlib.Path(app.config["FIT_STORAGE_DIR"]) / str(user)).exists()
    assert auth_client.get("/dashboard").status_code == 302  # signed out


def test_deleting_needs_password_and_confirmation(app, auth_client, user):
    auth_client.post("/settings/delete", data={"password": PASSWORD})
    auth_client.post("/settings/delete", data={"password": "wrong", "confirm": "y"})
    with app.app_context():
        assert db.session.get(User, user) is not None
