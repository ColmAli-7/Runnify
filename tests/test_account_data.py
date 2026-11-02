"""Data export and account deletion."""

import json
import pathlib
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from runnify.extensions import db, mail
from runnify.models import (
    FriendRequest,
    Playlist,
    PlaylistTrack,
    RecoveryCode,
    Run,
    RunLap,
    RunSongAnalysis,
    RunStream,
    SecurityEvent,
    Song,
    User,
    UserSongHistory,
)
from runnify.security.crypto import FERNET_PREFIX
from runnify.security.passwords import hash_password
from runnify.services import account
from runnify.services.account import json_chunks, to_json
from runnify.services.fit import Series, WatchLap
from runnify.services.streams import decode, save_stream
from tests.conftest import PASSWORD
from tests.factories import START, make_scored_run


def _seed(app, user_id):
    """Two runs (one recorded, with a lap and a scored play), a friend request and a FIT file.

    The play was skipped, the runner has a playlist of another song, and the account has
    a sign-in, the runner's consent and secrets that must stay out of the export.
    """
    with app.app_context():
        other = User(name="Friend", email="friend@example.com", password_hash=hash_password("x"))
        db.session.add(other)
        run = Run(
            user_id=user_id,
            activity_id="42",
            date_time=datetime(2026, 10, 1, 7),
            utc_offset=60,
            distance=5000,
            duration=1500,
            run_type="easy",
            laps_source="detected",
        )
        unrecorded = Run(
            user_id=user_id, activity_id="43", date_time=datetime(2026, 10, 2, 7), distance=3000
        )
        db.session.add_all(
            [
                run,
                unrecorded,
                Song(id="trk", name="Song", artist="Artist"),
                Song(id="listed", name="Listed", artist="Artist"),
            ]
        )
        db.session.flush()
        db.session.add(
            RunLap(
                run_id=run.id,
                position=0,
                start_second=0,
                end_second=1500,
                kind="steady",
                distance=5000,
                moving_seconds=1490,
                avg_hr=150,
            )
        )
        play = UserSongHistory(
            user_id=user_id,
            song_id="trk",
            run_id=run.id,
            played_at=datetime(2026, 10, 1, 7, 1),
            time_played=180,
            skipped=True,
        )
        db.session.add(play)
        db.session.flush()
        db.session.add_all(
            [
                RunSongAnalysis(
                    run_id=run.id,
                    user_song_id=play.id,
                    performance_score=61.5,
                    user_id=user_id,
                    seconds=170,
                    position=0.04,
                    method_version=3,
                ),
                FriendRequest(
                    sender_id=other.id, receiver_id=user_id, timestamp=datetime(2026, 10, 2, 8)
                ),
                SecurityEvent(
                    user_id=user_id,
                    kind="sign_in",
                    ip_prefix="203.0.113.0",
                    user_agent="Chrome on Windows",
                    created_at=datetime(2026, 10, 1, 6, 55),
                ),
                RecoveryCode(user_id=user_id, code_hash="secret-recovery-code"),
                RecoveryCode(
                    user_id=user_id, code_hash="secret-used-code", used_at=datetime(2026, 10, 5, 9)
                ),
                Playlist(
                    user_id=user_id,
                    name="Tempo",
                    session="tempo",
                    target_minutes=45,
                    created_at=datetime(2026, 10, 3, 18),
                    tracks=[
                        PlaylistTrack(position=0, song_id="listed", seconds=200, lift=7.5, plays=4)
                    ],
                ),
            ]
        )
        account = db.session.get(User, user_id)
        account.terms_accepted_at = datetime(2026, 9, 30, 20)
        account.data_consent_at = datetime(2026, 9, 30, 20, 1)
        account.spotify_token, account.spotify_refresh_token = "secret-access", "secret-refresh"
        account.garmin_tokens = "secret-garmin"
        account.garmin_password = "secret-legacy-password"  # erased by the next sync
        account.totp_secret, account.totp_enabled_at = "secret-totp", datetime(2026, 9, 30, 21)
        account.garmin_last_synced_at = datetime(2026, 10, 2, 9)
        account.history_imported_at = datetime(2026, 10, 1, 20)
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
        {
            "kind": "steady",
            "start_s": 0,
            "end_s": 1500,
            "distance_m": 5000,
            "moving_time_s": 1490,
            "average_heart_rate": 150,
        }
    ]
    assert data["song_plays_during_runs"][0]["track"] == "Song"
    assert data["song_plays_during_runs"][0]["garmin_activity_id"] == "42"
    assert data["song_scores"][0]["score"] == 61.5
    assert data["song_scores"][0]["garmin_activity_id"] == "42"
    body = response.get_data(as_text=True)
    with app.app_context():
        session_token = db.session.get(User, user).session_token
    for secret in (
        "secret-access",
        "secret-refresh",
        "secret-garmin",
        "secret-legacy-password",
        "secret-totp",
        "secret-recovery-code",
        "secret-used-code",
        session_token,
        FERNET_PREFIX,  # nor any encrypted column as stored
        "argon2",
        "password_hash",
        "session_token",
    ):
        assert secret not in body


def test_export_gives_consent_skips_and_browsers(app, auth_client, user):
    _seed(app, user)
    with app.app_context():  # agreed to an earlier policy, and not asked again yet
        db.session.get(User, user).policy_version = "2026-09"
        db.session.commit()
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    data = json.loads(response.data)
    assert data["account"]["two_step_verification"] is True
    assert data["account"]["consent"] == {
        "terms_accepted_at": "2026-09-30T20:00:00Z",
        "data_consent_at": "2026-09-30T20:01:00Z",
        "policy_version": "2026-09",  # the one agreed to, not the current one
    }
    assert data["song_plays_during_runs"][0]["skipped"] is True
    assert data["security_activity"] == [
        {
            "event": "Signed in",
            "at": "2026-10-01T06:55:00Z",
            "browser": "Chrome on Windows",
            "network": "203.0.113.0",
        }
    ]


def test_export_gives_score_details_and_account_dates(app, auth_client, user):
    _seed(app, user)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    data = json.loads(response.data)
    (play,), (score,) = data["song_plays_during_runs"], data["song_scores"]
    assert score["play_started_at"] == play["started_at"]  # which play it measured
    assert (score["moving_time_s"], score["position_in_run"], score["scoring_method"]) == (
        170,
        0.04,
        3,
    )
    account = data["account"]
    assert account["two_step_verification_since"] == "2026-09-30T21:00:00Z"
    assert account["recovery_codes_left"] == 1
    assert account["recovery_codes_used_at"] == ["2026-10-05T09:00:00Z"]
    assert account["garmin_last_synced_at"] == "2026-10-02T09:00:00Z"
    assert account["spotify_history_imported_at"] == "2026-10-01T20:00:00Z"


def test_export_gives_lap_sources_time_zones_and_playlist_settings(app, auth_client, user):
    _seed(app, user)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    data = json.loads(response.data)
    recorded, unrecorded = data["runs"]
    assert (recorded["laps_source"], recorded["utc_offset_minutes"]) == ("detected", 60)
    assert (unrecorded["laps_source"], unrecorded["utc_offset_minutes"]) == (None, None)
    assert data["playlists"] == [
        {
            "name": "Tempo",
            "session": "tempo",
            "target_minutes": 45,
            "created_at": "2026-10-03T18:00:00Z",
            "spotify_url": None,
            "spotify_track_ids": ["listed"],
            "track_seconds": [200],
            "track_lift_s_per_km": [7.5],
            "track_scored_plays": [4],
        }
    ]


def test_export_gives_the_friend_requests_still_waiting(app, auth_client, user):
    other = _seed(app, user)  # Friend has asked the runner
    with app.app_context():
        ann = User(name="Ann", email="ann@example.com", password_hash=hash_password("x"))
        db.session.add(ann)
        db.session.flush()
        db.session.add_all(
            [
                FriendRequest(
                    sender_id=user, receiver_id=ann.id, timestamp=datetime(2026, 10, 3, 9)
                ),
                FriendRequest(sender_id=user, receiver_id=other, status="declined"),
                FriendRequest(sender_id=ann.id, receiver_id=user, status="accepted"),
            ]
        )
        # Ann's two-step secret is under a key since retired, so only her name can be read
        db.session.execute(
            text("UPDATE users SET totp_secret = :secret WHERE id = :id"),
            {"secret": Fernet(Fernet.generate_key()).encrypt(b"x").decode(), "id": ann.id},
        )
        db.session.commit()
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    assert json.loads(response.data)["friend_requests"] == {
        "sent": [{"to": "Ann", "sent_at": "2026-10-03T09:00:00Z"}],
        "received": [{"from": "Friend", "sent_at": "2026-10-02T08:00:00Z"}],
    }


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


def test_export_is_sent_as_it_is_written_a_run_at_a_time(app, auth_client, user, monkeypatch):
    with app.app_context():
        for day in range(3):
            make_scored_run(user, start=START + timedelta(days=day), activity_id=f"run-{day}")
    decoded = []

    def counting_decode(*args, **kwargs):
        decoded.append(args[1])
        return decode(*args, **kwargs)

    monkeypatch.setattr(account, "decode", counting_decode)
    monkeypatch.setattr(account, "CHUNK_SIZE", 100)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    assert "Content-Length" not in response.headers  # streamed, not built first
    seen, body = [], b""
    for chunk in response.response:
        seen.append(len(decoded))
        body += chunk
    assert sorted(set(seen)) == [0, 1, 2, 3]  # pieces went out before, between and after the runs
    assert [run["garmin_activity_id"] for run in json.loads(body)["runs"]] == [
        "run-0",
        "run-1",
        "run-2",
    ]


def test_each_download_is_logged_before_it_is_sent(app, auth_client, user):
    first = auth_client.post("/settings/export", data={"password": PASSWORD})
    with app.app_context():  # committed by the view: nothing streamed writes
        assert SecurityEvent.query.filter_by(user_id=user, kind="data_exported").count() == 1
    assert json.loads(first.data)["security_activity"] == []  # a download doesn't list itself
    second = json.loads(auth_client.post("/settings/export", data={"password": PASSWORD}).data)
    assert [event["event"] for event in second["security_activity"]] == ["Account data downloaded"]


def test_a_download_failing_part_way_is_logged_and_never_valid_json(
    app, auth_client, user, monkeypatch
):
    _seed(app, user)

    def unreadable(*args, **kwargs):
        raise ValueError("stored stream unreadable")

    monkeypatch.setattr(account, "decode", unreadable)
    monkeypatch.setattr(account, "CHUNK_SIZE", 100)
    response = auth_client.post("/settings/export", data={"password": PASSWORD})
    assert response.status_code == 200  # on its way before the failure
    received = []
    with pytest.raises(ValueError, match="unreadable"):  # not swallowed: the server drops the line
        for chunk in response.response:
            received.append(chunk)
    assert received
    with pytest.raises(json.JSONDecodeError):
        json.loads(b"".join(received))
    with app.app_context():
        assert SecurityEvent.query.filter_by(user_id=user, kind="data_exported").count() == 1


def test_export_reads_the_history_a_batch_at_a_time(app, user, monkeypatch):
    monkeypatch.setattr(account, "RUN_BATCH", 2)
    monkeypatch.setattr(account, "ROW_BATCH", 3)
    names = [f"run-{day}" for day in range(5)]
    with app.app_context():
        for day, name in enumerate(names):
            make_scored_run(user, start=START + timedelta(days=day), activity_id=name)
        data = json.loads(to_json(account.export_data(db.session.get(User, user))))
    assert [run["garmin_activity_id"] for run in data["runs"]] == names
    assert all(len(run["samples"]["seconds"]) == 20 * 60 for run in data["runs"])
    plays = [play["garmin_activity_id"] for play in data["song_plays_during_runs"]]
    assert plays == [name for name in names for _ in range(4)]  # four songs a run
    scores = [score["garmin_activity_id"] for score in data["song_scores"]]
    assert scores == sorted(scores) and set(scores) == set(names)


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


def test_json_chunks_add_up_to_to_json_reading_each_list_as_they_reach_it(monkeypatch):
    monkeypatch.setattr(account, "CHUNK_SIZE", 16)
    runs = [{"seconds": [0, 1], "laps": [], "workout": None}, {"samples": {"pace": [300.5, None]}}]
    read = []

    def runs_as_read():
        for run in runs:
            read.append(run)
            yield run

    value = {"exported_at": "2026-11-02T12:00:00Z", "runs": runs_as_read(), "ids": iter([1, 2])}
    chunks = json_chunks(value)
    first = next(chunks)
    assert read == []  # the runs wait until the text reaches them
    chunks = [first, *chunks]
    assert "".join(chunks) == to_json({**value, "runs": runs, "ids": [1, 2]})
    assert all(len(chunk) >= 16 for chunk in chunks[:-1])
    assert to_json({"empty": iter([])}) == '{\n  "empty": []\n}'


def test_export_needs_the_password(auth_client):
    response = auth_client.post("/settings/export", data={"password": "wrong"})
    assert response.status_code == 302


def test_deleting_removes_everything_personal(app, auth_client, user):
    other = _seed(app, user)
    with app.app_context():  # a song the runner heard that the friend keeps in a playlist
        playlist = Playlist(user_id=other, name="Theirs", session="easy", target_minutes=30)
        db.session.add_all([playlist, Song(id="theirs", name="Kept", artist="Artist")])
        db.session.flush()
        db.session.add_all(
            [
                PlaylistTrack(playlist_id=playlist.id, position=0, song_id="theirs", seconds=200),
                UserSongHistory(
                    user_id=user,
                    song_id="theirs",
                    played_at=datetime(2026, 10, 2, 7, 1),
                    time_played=200,
                ),
            ]
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
            RecoveryCode,
        ):
            assert model.query.count() == 0, model.__name__
        assert [playlist.name for playlist in Playlist.query] == ["Theirs"]
        assert db.session.get(User, other) is not None  # the friend's account is untouched
        assert db.session.get(Song, "trk") is None  # nobody else's runs used it
        assert db.session.get(Song, "listed") is None  # only in the runner's own playlist
        assert db.session.get(Song, "theirs") is not None  # still in the friend's playlist
    assert not (pathlib.Path(app.config["FIT_STORAGE_DIR"]) / str(user)).exists()
    assert auth_client.get("/dashboard").status_code == 302  # signed out


def test_deleting_needs_password_and_confirmation(app, auth_client, user):
    auth_client.post("/settings/delete", data={"password": PASSWORD})
    auth_client.post("/settings/delete", data={"password": "wrong", "confirm": "y"})
    with app.app_context():
        assert db.session.get(User, user) is not None


def test_privacy_page_names_the_settings_rows_as_settings_does(auth_client):
    privacy = auth_client.get("/privacy").get_data(as_text=True)
    settings = auth_client.get("/settings").get_data(as_text=True)
    for row in ("Download your data", "Delete your account"):
        assert f"Settings, then {row}." in privacy
        assert f'<p class="settings__row-title">{row}</p>' in settings
