"""The playlist creator: selection, session shapes, saving and Spotify export."""

from datetime import timedelta

import pytest
import spotipy

from runnify.extensions import db
from runnify.models import Playlist, Run, RunSongAnalysis, Song, User, UserSongHistory, utcnow
from runnify.security.passwords import hash_password
from runnify.services import playlists as playlist_service
from runnify.services import spotify as spotify_service
from tests.conftest import sign_in_as

SONGS = {  # id: (lift in s/km on every play, plays, length in seconds, heart-rate change)
    "best": (15.0, 3, 240, 2.0),
    "good": (10.0, 3, 200, 8.0),
    "fine": (5.0, 3, 180, 0.0),
    "meh": (2.0, 3, None, 0.0),
    "slow": (-6.0, 3, 200, 0.0),
    "lucky": (25.0, 1, 200, 0.0),
}


@pytest.fixture
def library(app, user):
    with app.app_context():
        runs = [
            Run(
                user_id=user,
                activity_id=str(n),
                date_time=utcnow() - timedelta(days=n),
                duration=1800,
                distance=6000,
            )
            for n in range(1, 4)
        ]
        db.session.add_all(runs)
        for song_id, (_, _, length, _) in SONGS.items():
            db.session.add(Song(id=song_id, name=song_id.title(), artist="Artist", duration=length))
        db.session.flush()
        for song_id, (lift, plays, _, hr) in SONGS.items():
            for run in runs[:plays]:
                play = UserSongHistory(
                    user_id=user,
                    song_id=song_id,
                    run_id=run.id,
                    played_at=run.date_time,
                    time_played=180,
                )
                db.session.add(play)
                db.session.flush()
                db.session.add(
                    RunSongAnalysis(
                        run_id=run.id,
                        user_song_id=play.id,
                        user_id=user,
                        performance_score=50,
                        pace_delta=lift,
                        hr_delta=hr,
                        seconds=180,
                        position=0.5,
                        method_version=2,
                    )
                )
        db.session.commit()
    return user


def _keys(result):
    return [t.song.id for t in result.tracks]


def test_only_proven_helpful_songs_are_chosen(app, library):
    with app.app_context():
        chosen = set(_keys(playlist_service.plan(library, "tempo", 120)))
        assert chosen == {"best", "good", "fine", "meh"}  # not the slow song, not the one-off


def test_untested_songs_can_be_included(app, library):
    with app.app_context():
        assert "lucky" in _keys(playlist_service.plan(library, "tempo", 120, include_untested=True))


def test_tempo_builds_and_race_saves_the_best_for_last(app, library):
    with app.app_context():
        assert _keys(playlist_service.plan(library, "tempo", 120))[-1] == "best"
        race = _keys(playlist_service.plan(library, "race", 120))
        assert race[-1] == "best" and race[-2] == "good"


def test_intervals_alternate_strong_and_calm(app, library):
    with app.app_context():
        assert _keys(playlist_service.plan(library, "intervals", 120)) == [
            "best",
            "fine",
            "good",
            "meh",
        ]


def test_easy_runs_deprioritise_heart_rate_raisers(app, library):
    with app.app_context():
        # "good" lifts pace more than "fine" but raises heart rate by 8 bpm, so for an
        # easy run it ranks below "fine"; a two-song playlist shows the ranking
        assert set(_keys(playlist_service.plan(library, "easy", 7))) == {"best", "fine"}


def test_playlists_fit_the_target_and_explain_shortfalls(app, library):
    with app.app_context():
        short = playlist_service.plan(library, "tempo", 7)
        assert short.total_seconds >= 7 * 60 and len(short.tracks) == 2
        long = playlist_service.plan(library, "tempo", 120)
        assert long.total_seconds == 240 + 200 + 180 + 210  # unknown length counts as 3.5 minutes
        assert "instead of 120" in long.note


def test_no_scored_songs_explains_why(app, user):
    with app.app_context():
        result = playlist_service.plan(user, "tempo", 45)
        assert result.tracks == [] and "enough scored songs" in result.note


def test_build_save_view_and_delete(app, auth_client, library):
    response = auth_client.post("/playlists", data={"session": "race", "minutes": "30"})
    assert response.status_code == 302
    with app.app_context():
        playlist = Playlist.query.one()
        assert playlist.name == "Runnify race, 30 min"
        playlist_id = playlist.id
    assert b"Best" in auth_client.get(f"/playlists/{playlist_id}").data
    auth_client.post(f"/playlists/{playlist_id}/delete")
    with app.app_context():
        assert Playlist.query.count() == 0


def test_other_users_playlists_are_not_found(app, client, library):
    with app.app_context():
        result = playlist_service.plan(library, "tempo", 30)
        playlist = playlist_service.save(db.session.get(User, library), result)
        intruder = User(name="I", email="i@example.com", password_hash=hash_password("x"))
        intruder.record_consent()
        db.session.add(intruder)
        db.session.commit()
        playlist_id, intruder_id = playlist.id, intruder.id
    sign_in_as(client, intruder_id)
    assert client.get(f"/playlists/{playlist_id}").status_code == 404
    assert client.post(f"/playlists/{playlist_id}/delete").status_code == 404


class FakeSpotify:
    def __init__(self, fail=None):
        self.fail, self.added = fail, []

    def current_user(self):
        return {"id": "runner"}

    def user_playlist_create(self, user, name, public, description):
        if self.fail:
            raise self.fail
        assert public is False
        return {"id": "pl1", "external_urls": {"spotify": "https://open.spotify.com/playlist/pl1"}}

    def playlist_add_items(self, playlist_id, uris):
        self.added.append(list(uris))


def test_send_to_spotify_creates_a_private_playlist(app, library, monkeypatch):
    fake = FakeSpotify()
    monkeypatch.setattr(spotify_service, "client_for", lambda user: fake)
    monkeypatch.setattr(playlist_service, "SPOTIFY_BATCH", 3)
    with app.app_context():
        account = db.session.get(User, library)
        playlist = playlist_service.save(account, playlist_service.plan(library, "tempo", 120))
        playlist_service.send_to_spotify(account, playlist)
        assert playlist.spotify_url == "https://open.spotify.com/playlist/pl1"
        assert [len(batch) for batch in fake.added] == [3, 1]
        assert fake.added[0][0].startswith("spotify:track:")


def test_spotify_errors_become_clear_messages(app, library, monkeypatch):
    with app.app_context():
        account = db.session.get(User, library)
        playlist = playlist_service.save(account, playlist_service.plan(library, "tempo", 30))
        monkeypatch.setattr(spotify_service, "client_for", lambda user: None)
        with pytest.raises(playlist_service.SpotifyExportError, match="Connect Spotify"):
            playlist_service.send_to_spotify(account, playlist)
        denied = spotipy.SpotifyException(403, -1, "insufficient scope")
        monkeypatch.setattr(spotify_service, "client_for", lambda user: FakeSpotify(fail=denied))
        with pytest.raises(playlist_service.SpotifyExportError, match="Reconnect Spotify"):
            playlist_service.send_to_spotify(account, playlist)
        timeout = FakeSpotify(fail=TimeoutError())
        monkeypatch.setattr(spotify_service, "client_for", lambda user: timeout)
        with pytest.raises(playlist_service.SpotifyExportError, match="couldn't be reached"):
            playlist_service.send_to_spotify(account, playlist)
