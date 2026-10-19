"""Synthetic demo data for local development and previews (never production).

``flask --app runnify demo seed`` creates a demo account with four months of
runs: second-by-second pace and heart rate with warm-ups, fatigue, hills,
traffic-light stops and noise, and songs played through each run. Easy, long
and tempo runs are steady; interval sessions and run-walks have parts, with
heart rate that lags the effort, and half of them carry the watch's laps
while the rest leave the laps to be found. Every song has a hidden "true"
effect on pace; the real scoring pipeline then has to recover it, so the demo
doubles as an end-to-end check of the analytics.
Friends, a pending friend request and a playlist are added too.
Deterministic: the same data every time.
"""

import hashlib
import math
import random
from datetime import timedelta

from runnify.extensions import db
from runnify.models import FriendRequest, Run, Song, User, UserSongHistory, utcnow
from runnify.security.passwords import hash_password
from runnify.services import playlists as playlist_service
from runnify.services.account import delete_account
from runnify.services.analysis import rescore_run
from runnify.services.fit import Series, WatchLap
from runnify.services.streams import save_stream

DEMO_EMAIL = "demo@runnify.test"
FRIEND_DOMAIN = "friends.runnify.test"
RUN_KINDS = ("easy", "intervals", "easy", "long", "tempo", "run_walk")
SESSIONS = ("intervals", "run_walk")  # runs with parts, simulated by _simulate_session
# each part of a session: pace (s/km, None for a walk) and heart rate (bpm) against the
# runner's base for the day
SESSION_PARTS = {
    "warmup": (25, 2),
    "hard": (-55, 38),
    "jog": (45, 14),
    "cooldown": (30, 4),
    "run": (12, 10),
    "walk": (None, -18),
}
INTENSITIES = {  # how a watch following the workout marks each part's lap
    "warmup": "warmup",
    "hard": "active",
    "jog": "rest",
    "cooldown": "cooldown",
    "run": "active",
    "walk": "rest",
}
WALK_PACE = 660.0  # s/km, 11:00/km

# title, artist, length (s), true pace effect (s/km faster), heart-rate effect (bpm)
SONGS = [
    ("Mr. Brightside", "The Killers", 222, 11, 3),
    ("Titanium", "David Guetta, Sia", 245, 8, 2),
    ("Lose Yourself", "Eminem", 326, 9, 5),
    ("Till I Collapse", "Eminem", 297, 10, 4),
    ("Can't Hold Us", "Macklemore & Ryan Lewis", 258, 12, 4),
    ("Don't Stop Me Now", "Queen", 209, 7, 2),
    ("Eye of the Tiger", "Survivor", 245, 5, 1),
    ("Stronger", "Kanye West", 312, 6, 3),
    ("Blinding Lights", "The Weeknd", 200, 6, 1),
    ("Levitating", "Dua Lipa", 203, 4, 1),
    ("Seven Nation Army", "The White Stripes", 232, 3, 2),
    ("Run Boy Run", "Woodkid", 222, 9, 2),
    ("Power", "Kanye West", 292, 5, 3),
    ("Uprising", "Muse", 304, 4, 1),
    ("Midnight City", "M83", 244, 3, 0),
    ("Dog Days Are Over", "Florence + The Machine", 252, 6, 2),
    ("Shake It Off", "Taylor Swift", 219, 2, 0),
    ("Mo Bamba", "Sheck Wes", 183, 7, 6),
    ("Breathe", "The Prodigy", 335, 5, 4),
    ("Jump Around", "House of Pain", 215, 4, 3),
    ("Holocene", "Bon Iver", 336, -9, -2),
    ("Skinny Love", "Bon Iver", 238, -7, -1),
    ("Retrograde", "James Blake", 223, -6, -1),
    ("Hallelujah", "Jeff Buckley", 414, -10, -3),
    ("The Night We Met", "Lord Huron", 208, -8, -2),
    ("Lovely", "Billie Eilish, Khalid", 200, -5, -1),
    ("Strobe", "deadmau5", 637, 1, 0),
    ("Get Lucky", "Daft Punk", 369, 2, 0),
    ("Bad Guy", "Billie Eilish", 194, 1, 0),
    ("Heads Will Roll", "Yeah Yeah Yeahs", 221, 5, 2),
    ("Sandstorm", "Darude", 225, 8, 5),
    ("Feel It Still", "Portugal. The Man", 163, 2, 0),
]

FRIENDS = [("Aoife Byrne", 412_000), ("Tomás Kelly", 288_000), ("Sam Okafor", 351_000)]
REQUESTER = "Niamh Walsh"


class DemoError(RuntimeError):
    """The demo can't be seeded here (e.g. in production)."""


def _song_id(title, artist):
    """A stable fake track id (demo tracks don't exist on Spotify)."""
    return "demo" + hashlib.sha256(f"{title}|{artist}".encode()).hexdigest()[:18]


def _run_profile(rng, kind):
    """Base pace (s/km), distance (m) and base heart rate for a kind of run."""
    if kind == "tempo":
        return rng.uniform(268, 284), rng.uniform(7000, 10000), 150
    if kind == "long":
        return rng.uniform(312, 330), rng.uniform(15000, 21100), 138
    return rng.uniform(318, 340), rng.uniform(5000, 9000), 132


def _plan(rng, kind):
    """The parts of an interval session or a run-walk, as ``(seconds, part)``."""
    if kind == "intervals":
        reps, rep, jog = rng.choice(((6, 180, 120), (8, 120, 90), (5, 240, 150)))
        return [(600, "warmup")] + [(rep, "hard"), (jog, "jog")] * reps + [(600, "cooldown")]
    run, walk = rng.choice(((240, 60), (300, 60), (180, 45)))
    return [(run, "run"), (walk, "walk")] * rng.randint(7, 9)


def _next_song(rng, queue, index, second, plays):
    """Start the next song in ``queue`` at ``second``; returns its index and when it ends."""
    index = (index + 1) % len(queue)
    skipped = rng.random() < 0.1
    length = rng.randint(15, 60) if skipped else queue[index][1]
    plays.append([queue[index][0], second, length, skipped])
    return index, second + length


def _simulate_session(rng, start, kind, songs, watch_laps):
    """An interval session or a run-walk, second by second (see :func:`_simulate`).

    Heart rate eases towards each part's effort over about half a minute, as
    it does, rather than jumping with the pace. With ``watch_laps`` the series
    carries the watch's laps for the plan, as a watch following a workout
    records them; without, the laps have to be found from the run.
    """
    base_pace, base_hr = rng.uniform(300, 325), rng.uniform(128, 136)
    plan = _plan(rng, kind)
    queue = rng.sample(songs, k=len(songs))
    paces, heart_rates, timestamps, plays, laps = [], [], [], [], []
    index, song_end, metres, heart, second = -1, 0, 0.0, base_hr, 0
    for step, (seconds, part) in enumerate(plan):
        laps.append(WatchLap(second, second + seconds, INTENSITIES[part], "time", step))
        pace_offset, hr_offset = SESSION_PARTS[part]
        for _ in range(seconds):
            if second >= song_end:
                index, song_end = _next_song(rng, queue, index, second, plays)
            _song, _length, effect, hr_effect = queue[index]
            effect = 0 if plays[-1][3] else effect
            if pace_offset is None:  # walking: music or not, it's a walk
                pace, hr_effect = WALK_PACE + rng.gauss(0, 15), 0
            else:
                pace = base_pace + pace_offset - effect + rng.gauss(0, 5)
            heart += (base_hr + hr_offset + hr_effect - heart) / 30
            paces.append(round(pace, 1))
            metres += 1000 / pace
            heart_rates.append(round(heart + rng.gauss(0, 1.5)))
            timestamps.append(start + timedelta(seconds=second))
            second += 1
    plays[-1][2] = min(plays[-1][2], second - plays[-1][1])
    series = Series(
        timestamps=timestamps,
        heart_rates=heart_rates,
        paces=paces,
        laps=laps if watch_laps else [],
    )
    return series, plays, metres, second, round(sum(heart_rates) / len(heart_rates))


def _simulate(rng, start, kind, songs, watch_laps=False):
    """Simulate one run second by second.

    Args:
        rng: The random generator.
        start: When the run starts.
        kind: "easy", "tempo", "long", "intervals" or "run_walk".
        songs: ``(Song, length, pace effect, hr effect)`` tuples to play from.
        watch_laps: For a session, whether the watch recorded its laps.

    Returns:
        ``(series, plays, metres, seconds, average_hr)`` where plays are
        ``(song, start_second, seconds_played, skipped)``.
    """
    if kind in SESSIONS:
        return _simulate_session(rng, start, kind, songs, watch_laps)
    base_pace, target_m, base_hr = _run_profile(rng, kind)
    hill_period, hill_phase = rng.uniform(420, 900), rng.uniform(0, 2 * math.pi)
    stops = {rng.randrange(600, 2400) for _ in range(rng.randint(0, 3))}
    queue = rng.sample(songs, k=len(songs))
    paces, heart_rates, timestamps, plays = [], [], [], []
    index, song_end, stopped_until, metres, second = -1, 0, -1, 0.0, 0

    while metres < target_m:
        if second >= song_end:  # the next song starts
            index = (index + 1) % len(queue)
            skipped = rng.random() < 0.1
            length = rng.randint(15, 60) if skipped else queue[index][1]
            plays.append([queue[index][0], second, length, skipped])
            song_end = second + length
        _song, _length, effect, hr_effect = queue[index]
        effect = 0 if plays[-1][3] else effect  # a skipped song has no time to work
        effect *= 0.7 + 0.8 * metres / target_m  # this runner gets more from music when tired
        km = metres / 1000
        pace = (
            base_pace
            + 26 * math.exp(-second / 240)  # warm-up
            + 0.9 * max(0.0, km - 8)  # fatigue on longer runs
            + 7 * math.sin(second / hill_period * 2 * math.pi + hill_phase)  # rolling hills
            - effect
            + rng.gauss(0, 5)
        )
        hr = base_hr + 14 * (1 - math.exp(-second / 300)) + 0.6 * km + hr_effect + rng.gauss(0, 1.5)
        if second in stops:
            stopped_until = second + rng.randint(25, 70)  # traffic lights
        if second < stopped_until:
            paces.append(None)
            hr -= 8
        else:
            paces.append(round(pace, 1))
            metres += 1000 / pace
        heart_rates.append(round(hr))
        timestamps.append(start + timedelta(seconds=second))
        second += 1

    plays[-1][2] = min(plays[-1][2], second - plays[-1][1])  # the finish cuts off the last song
    series = Series(timestamps=timestamps, heart_rates=heart_rates, paces=paces)
    return series, plays, metres, second, round(sum(heart_rates) / len(heart_rates))


def _clear_previous():
    for user in User.query.filter(
        (User.email == DEMO_EMAIL) | User.email.like(f"%@{FRIEND_DOMAIN}")
    ).all():
        delete_account(user)
    db.session.commit()


def _friend(name, index, password):
    friend = User(
        name=name,
        email=f"friend{index}@{FRIEND_DOMAIN}",
        password_hash=hash_password(f"{password}-{index}"),
    )
    friend.record_consent()
    db.session.add(friend)
    db.session.flush()
    return friend


def seed(app, password, now=None):
    """Create (or recreate) the demo account and its data; returns the demo user."""
    if app.config["ENV_NAME"] == "production":
        raise DemoError("Refusing to seed demo data in production.")
    rng = random.Random(20261009)  # noqa: S311  (a repeatable simulation, not security)
    now = now or utcnow()
    _clear_previous()

    user = User(name="Colm Ali", email=DEMO_EMAIL, password_hash=hash_password(password))
    user.record_consent()
    user.garmin_username = "colm@example.com"
    user.garmin_sync_state = "ok"
    user.garmin_last_synced_at = now - timedelta(minutes=12)
    user.history_import_state = "ok"
    user.history_imported_at = now - timedelta(days=2)
    db.session.add(user)
    db.session.flush()

    songs = []
    for title, artist, length, effect, hr_effect in SONGS:
        song = db.session.get(Song, _song_id(title, artist)) or Song(id=_song_id(title, artist))
        song.name, song.artist, song.duration = title, artist, length
        db.session.add(song)
        songs.append((song, length, effect, hr_effect))
    db.session.flush()

    play_count = 0
    for n in range(36):
        day = now - timedelta(days=120 - n * 3 - rng.randint(0, 1))
        start = day.replace(
            hour=rng.choice((6, 7, 7, 12, 18, 19)),
            minute=rng.randint(0, 59),
            second=0,
            microsecond=0,
        )
        kind = RUN_KINDS[n % len(RUN_KINDS)]
        watch_laps = (n // len(RUN_KINDS)) % 2 == 0  # every other session recorded its laps
        series, plays, metres, seconds, avg_hr = _simulate(rng, start, kind, songs, watch_laps)
        run = Run(
            user_id=user.id,
            activity_id=f"demo-{n:03d}",
            date_time=start,
            utc_offset=60,  # Irish summer time
            distance=round(metres, 1),
            duration=seconds,
            avg_hr=avg_hr,
            avg_pace=seconds / (metres / 1000) / 60,
        )
        db.session.add(run)
        db.session.flush()
        save_stream(run, series)
        for song, song_start, length, skipped in plays:
            db.session.add(
                UserSongHistory(
                    user_id=user.id,
                    song_id=song.id,
                    run_id=run.id,
                    played_at=start + timedelta(seconds=song_start),
                    time_played=length,
                    skipped=skipped,
                )
            )
            play_count += 1
        db.session.flush()
        rescore_run(run, series)

    user.garmin_sync_message = "36 new runs imported."
    user.history_import_message = f"Matched {play_count} song plays to your runs."

    for index, (name, total_m) in enumerate(FRIENDS):
        friend = _friend(name, index, password)
        for week in range(8):
            db.session.add(
                Run(
                    user_id=friend.id,
                    activity_id=f"friend{index}-{week}",
                    date_time=now - timedelta(days=week * 7 + index),
                    distance=total_m / 8,
                    duration=int(total_m / 8 / 1000 * 300),
                )
            )
        user.friends.append(friend)
        friend.friends.append(user)
    requester = _friend(REQUESTER, 9, password)
    db.session.add(FriendRequest(sender_id=requester.id, receiver_id=user.id))
    db.session.flush()

    plan = playlist_service.plan(user.id, "tempo", 45)
    if plan.tracks:
        playlist_service.save(user, plan)
    db.session.commit()
    return user
