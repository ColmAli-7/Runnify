"""Findings across a runner's songs and runs (the Insights page, dashboard and playlists).

Every aggregate is honest about its evidence:

* a song's effect is the moving-time-weighted mean of its per-run effects;
* rankings use a *shrunk* effect, pulled towards zero by ``PRIOR_PLAYS``
  imaginary neutral plays, so a single lucky play can't top the chart;
* each finding carries its number of plays and a confidence level.

All grouping happens in Python, so it works the same on SQLite and PostgreSQL.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory, utcnow

PRIOR_PLAYS = 2  # shrinkage strength: imaginary plays with no effect added to every song
MIN_PLAYS_TO_RANK = 2
RANGES = {
    "30d": ("Last 30 days", 30),
    "90d": ("Last 90 days", 90),
    "year": ("This year", None),
    "all": ("All time", None),
}
DEFAULT_RANGE = "90d"
PHASES = (("Start", 0.0, 0.2), ("Middle", 0.2, 0.8), ("Finish", 0.8, 1.01))


def range_start(key, now=None):
    """Earliest run start included by the range ``key`` (``None`` = no limit)."""
    now = now or utcnow()
    if key == "year":
        return datetime(now.year, 1, 1)
    days = RANGES.get(key, RANGES[DEFAULT_RANGE])[1]
    return now - timedelta(days=days) if days else None


def confidence(plays):
    """How much to trust an aggregate built from ``plays`` scored plays."""
    if plays >= 5:
        return "high"
    if plays >= MIN_PLAYS_TO_RANK:
        return "medium"
    return "low"


@dataclass
class Effect:
    """An aggregated effect for one song, artist or group."""

    key: str
    label: str
    detail: str = ""
    plays: int = 0
    seconds: int = 0
    lift: float = 0.0  # weighted mean s/km faster (+) or slower (-)
    hr_delta: float | None = None
    skips: int = 0
    runs: set = field(default_factory=set)

    @property
    def shrunk_lift(self):
        """The lift pulled towards zero in proportion to how little evidence there is."""
        return self.lift * self.plays / (self.plays + PRIOR_PLAYS)

    @property
    def confidence(self):
        return confidence(self.plays)

    @property
    def score(self):
        """The lift on the familiar 0-100 scale (50 = no effect; 10 s/km is about 20 points)."""
        return round(max(0.0, min(100.0, 50 + 2 * self.shrunk_lift)), 1)


def _rows(user_id, since=None):
    """Scored plays for ``user_id`` as ``(analysis, play, song, run)`` tuples."""
    query = (
        db.session.query(RunSongAnalysis, UserSongHistory, Song, Run)
        .join(UserSongHistory, UserSongHistory.id == RunSongAnalysis.user_song_id)
        .join(Song, Song.id == UserSongHistory.song_id)
        .join(Run, Run.id == RunSongAnalysis.run_id)
        .filter(RunSongAnalysis.user_id == user_id, RunSongAnalysis.pace_delta.isnot(None))
    )
    if since is not None:
        query = query.filter(Run.date_time >= since)
    return query.all()


def _aggregate(rows, key_of, label_of, detail_of=lambda song: ""):
    groups = {}
    hr_weights = defaultdict(lambda: [0.0, 0.0])  # key -> [weighted hr sum, weight]
    for analysis, play, song, run in rows:
        key = key_of(song)
        if key is None:
            continue
        effect = groups.setdefault(
            key, Effect(key=key, label=label_of(song), detail=detail_of(song))
        )
        weight = max(analysis.seconds or 0, 1)
        effect.lift = (effect.lift * effect.seconds + analysis.pace_delta * weight) / (
            effect.seconds + weight
        )
        effect.seconds += weight
        effect.plays += 1
        effect.skips += bool(play.skipped)
        effect.runs.add(run.id)
        if analysis.hr_delta is not None:
            hr_weights[key][0] += analysis.hr_delta * weight
            hr_weights[key][1] += weight
    for key, (total, weight) in hr_weights.items():
        groups[key].hr_delta = total / weight if weight else None
    return list(groups.values())


def song_effects(user_id, since=None):
    """Every scored song for ``user_id`` (optionally only runs since ``since``)."""
    return _aggregate(
        _rows(user_id, since),
        key_of=lambda song: song.id,
        label_of=lambda song: song.name or "Unknown track",
        detail_of=lambda song: song.artist or "",
    )


def artist_effects(user_id, since=None):
    """Every artist with scored plays for ``user_id``."""
    return _aggregate(
        _rows(user_id, since),
        key_of=lambda song: (song.artist or "").strip() or None,
        label_of=lambda song: song.artist,
    )


def _ranked(effects, best=True, limit=5):
    pool = [e for e in effects if e.plays >= MIN_PLAYS_TO_RANK]
    pool = [e for e in pool if (e.shrunk_lift > 0 if best else e.shrunk_lift < 0)]
    return sorted(pool, key=lambda e: e.shrunk_lift, reverse=best)[:limit]


@dataclass
class Overview:
    """Everything the Insights page shows for one date range."""

    range_key: str
    range_label: str
    plays: int
    songs: int
    runs_with_music: int
    music_seconds: int
    average_lift: float | None
    power_songs: list
    drag_songs: list
    top_artists: list
    phases: list  # (label, plays, weighted lift)
    heart_raisers: list
    most_skipped: list
    monthly: list  # (YYYY-MM, weighted lift, plays)
    with_music_pace: float | None
    without_music_pace: float | None

    @property
    def has_data(self):
        return self.plays > 0


def _weighted_mean(pairs):
    total_weight = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total_weight if total_weight else None


def _run_paces(user_id, since):
    """Average pace (s/km) of runs with and without matched music in the range."""
    runs = Run.query.filter(Run.user_id == user_id, Run.distance > 0, Run.duration > 0)
    if since is not None:
        runs = runs.filter(Run.date_time >= since)
    with_music_ids = {
        run_id
        for (run_id,) in db.session.query(UserSongHistory.run_id)
        .filter(UserSongHistory.user_id == user_id, UserSongHistory.run_id.isnot(None))
        .distinct()
    }
    groups = {True: [], False: []}
    for run in runs:
        groups[run.id in with_music_ids].append(
            (run.duration / (run.distance / 1000), run.distance)
        )
    return _weighted_mean(groups[True]), _weighted_mean(groups[False])


def overview(user_id, range_key=DEFAULT_RANGE):
    """Compute every finding for ``user_id`` over ``range_key`` (see :data:`RANGES`)."""
    range_key = range_key if range_key in RANGES else DEFAULT_RANGE
    since = range_start(range_key)
    rows = _rows(user_id, since)
    songs = _aggregate(
        rows, lambda s: s.id, lambda s: s.name or "Unknown track", lambda s: s.artist or ""
    )
    artists = _aggregate(rows, lambda s: (s.artist or "").strip() or None, lambda s: s.artist)

    phase_pairs = {label: [] for label, _, _ in PHASES}
    monthly = defaultdict(list)
    for analysis, _play, _song, run in rows:
        weight = max(analysis.seconds or 0, 1)
        for label, low, high in PHASES:
            if low <= (analysis.position or 0.0) < high:
                phase_pairs[label].append((analysis.pace_delta, weight))
        monthly[run.date_time.strftime("%Y-%m")].append((analysis.pace_delta, weight))

    with_music, without_music = _run_paces(user_id, since)
    heart_raisers = sorted(
        (s for s in songs if s.plays >= MIN_PLAYS_TO_RANK and (s.hr_delta or 0) > 0),
        key=lambda s: s.hr_delta,
        reverse=True,
    )[:5]
    most_skipped = sorted(
        (s for s in songs if s.skips), key=lambda s: (s.skips, s.plays), reverse=True
    )[:5]

    return Overview(
        range_key=range_key,
        range_label=RANGES[range_key][0],
        plays=len(rows),
        songs=len(songs),
        runs_with_music=len({run.id for *_, run in rows}),
        music_seconds=sum(analysis.seconds or 0 for analysis, *_ in rows),
        average_lift=_weighted_mean([(a.pace_delta, max(a.seconds or 0, 1)) for a, *_ in rows]),
        power_songs=_ranked(songs, best=True),
        drag_songs=_ranked(songs, best=False),
        top_artists=_ranked(artists, best=True),
        phases=[(label, len(pairs), _weighted_mean(pairs)) for label, pairs in phase_pairs.items()],
        heart_raisers=heart_raisers,
        most_skipped=most_skipped,
        monthly=[
            (month, _weighted_mean(pairs), len(pairs)) for month, pairs in sorted(monthly.items())
        ],
        with_music_pace=with_music,
        without_music_pace=without_music,
    )
