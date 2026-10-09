"""Building playlists from the songs that measurably help the runner.

A playlist is chosen from the runner's own song effects (see
:mod:`runnify.services.insights`) and shaped for the session:

* **easy**: steady energy; songs that push heart rate up are deprioritised.
* **tempo**: builds, so the strongest songs arrive as the effort rises.
* **long**: steady, with the strongest songs held back for the final stretch.
* **race**: strong throughout, the very best saved for the finish.
* **intervals**: alternates the hardest-working songs (efforts) with calmer
  ones (recoveries).

Track lengths come from the runner's history (plays that ran to the end);
unknown lengths count as 3.5 minutes. Songs are never repeated: if the proven
songs can't fill the target time, the playlist is shorter and says why.
"""

from dataclasses import dataclass, field

import spotipy

from runnify.extensions import db
from runnify.models import Playlist, PlaylistTrack, Song
from runnify.services import insights
from runnify.services import spotify as spotify_service

DEFAULT_TRACK_SECONDS = 210
SPOTIFY_BATCH = 100  # most tracks Spotify accepts per request

SESSIONS = {
    "easy": "Easy run",
    "tempo": "Tempo run",
    "long": "Long run",
    "race": "Race",
    "intervals": "Intervals",
}
DURATIONS = (20, 30, 45, 60, 75, 90, 120)


@dataclass
class PlannedTrack:
    """A song chosen for a playlist, and the evidence it was chosen on."""

    song: Song
    seconds: int
    lift: float
    plays: int


@dataclass
class PlaylistPlan:
    """The outcome of :func:`plan`: an ordered set of tracks, or a reason there are none."""

    session: str
    target_minutes: int
    tracks: list[PlannedTrack] = field(default_factory=list)
    note: str | None = None

    @property
    def total_seconds(self):
        return sum(track.seconds for track in self.tracks)


def _rank_key(session):
    if session == "easy":  # favour songs that help without raising heart rate much
        return lambda effect: effect.shrunk_lift - 0.5 * max(effect.hr_delta or 0.0, 0.0)
    return lambda effect: effect.shrunk_lift


def _order(session, chosen):
    """Arrange chosen tracks (best first on entry) to suit the session."""
    if session == "tempo":
        return sorted(chosen, key=lambda t: t.lift)
    if session in {"long", "race"}:
        held_back = 2 if session == "race" else max(1, len(chosen) // 5)
        best, rest = chosen[:held_back], chosen[held_back:]
        rest = (
            rest[::2] + rest[1::2][::-1] if session == "long" else rest
        )  # long: spread the middle
        return rest + best[::-1]
    if session == "intervals":
        ordered, strong, calm = (
            [],
            chosen[: (len(chosen) + 1) // 2],
            chosen[(len(chosen) + 1) // 2 :],
        )
        for i in range(len(chosen)):
            pool = strong if i % 2 == 0 else calm
            if not pool:
                pool = strong or calm
            ordered.append(pool.pop(0))
        return ordered
    return chosen[::2] + chosen[1::2]  # easy: alternate so strong songs are spread out


def plan(user_id, session, target_minutes, include_untested=False):
    """Choose and order songs for a ``session`` of ``target_minutes``.

    Args:
        user_id: Whose songs to use.
        session: One of :data:`SESSIONS`.
        target_minutes: Desired playlist length.
        include_untested: Also consider songs with only one scored play.
    """
    if session not in SESSIONS:
        raise ValueError(f"unknown session {session!r}")
    minimum = 1 if include_untested else insights.MIN_PLAYS_TO_RANK
    effects = [
        e
        for e in insights.song_effects(user_id)
        if e.plays >= minimum and e.shrunk_lift > (-1.0 if session == "easy" else 0.0)
    ]
    result = PlaylistPlan(session=session, target_minutes=target_minutes)
    if not effects:
        result.note = (
            "There aren't enough scored songs yet. Import more listening history, "
            "or include songs heard on only one run."
        )
        return result

    effects.sort(key=_rank_key(session), reverse=True)
    songs = {s.id: s for s in Song.query.filter(Song.id.in_([e.key for e in effects]))}
    target = target_minutes * 60
    chosen = []
    for effect in effects:
        if sum(t.seconds for t in chosen) >= target:
            break
        song = songs[effect.key]
        chosen.append(
            PlannedTrack(
                song=song,
                seconds=song.duration or DEFAULT_TRACK_SECONDS,
                lift=round(effect.shrunk_lift, 1),
                plays=effect.plays,
            )
        )
    result.tracks = _order(session, chosen)
    if result.total_seconds < target * 0.9:
        minutes = round(result.total_seconds / 60)
        result.note = (
            f"Only {len(chosen)} songs have enough evidence, so this playlist runs "
            f"{minutes} minutes instead of {target_minutes}."
        )
    return result


def save(user, result):
    """Store a :class:`PlaylistPlan` for ``user`` and return the new :class:`Playlist`."""
    playlist = Playlist(
        user_id=user.id,
        name=f"Runnify {SESSIONS[result.session].lower()}, {result.target_minutes} min",
        session=result.session,
        target_minutes=result.target_minutes,
    )
    playlist.tracks = [
        PlaylistTrack(position=i, song_id=t.song.id, seconds=t.seconds, lift=t.lift, plays=t.plays)
        for i, t in enumerate(result.tracks)
    ]
    db.session.add(playlist)
    return playlist


class SpotifyExportError(Exception):
    """Sending a playlist to Spotify failed (the message is safe to show)."""


def send_to_spotify(user, playlist):
    """Create ``playlist`` as a private playlist in the user's Spotify account.

    Raises:
        SpotifyExportError: Spotify isn't connected, refused the request, or
            couldn't be reached.
    """
    client = spotify_service.client_for(user)
    if client is None:
        raise SpotifyExportError("Connect Spotify first.")
    description = (
        f"Built by Runnify from the songs that lift your pace. {len(playlist.tracks)} tracks."
    )
    uris = [f"spotify:track:{track.song_id}" for track in playlist.tracks]
    try:
        me = client.current_user()
        created = client.user_playlist_create(
            me["id"], playlist.name, public=False, description=description
        )
        for i in range(0, len(uris), SPOTIFY_BATCH):
            client.playlist_add_items(created["id"], uris[i : i + SPOTIFY_BATCH])
    except spotipy.SpotifyException as error:
        if error.http_status in (401, 403):
            raise SpotifyExportError(
                "Spotify didn't allow Runnify to create playlists. Reconnect Spotify and try again."
            ) from error
        raise SpotifyExportError("Spotify couldn't create the playlist right now.") from error
    except Exception as error:  # network failures, timeouts
        raise SpotifyExportError("Spotify couldn't be reached. Please try again later.") from error
    playlist.spotify_playlist_id = created["id"]
    playlist.spotify_url = (created.get("external_urls") or {}).get("spotify")
    return playlist
