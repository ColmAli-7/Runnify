"""Findings across a runner's songs and runs (the Insights page, dashboard and playlists).

Every aggregate is honest about its evidence:

* a song's effect is the moving-time-weighted mean of its per-run effects;
* rankings use a *shrunk* effect, pulled towards zero by ``PRIOR_PLAYS``
  imaginary neutral plays, so a single lucky play can't top the chart;
* each finding carries its number of plays and a confidence level;
* skips are counted over every play during a run, measured or not, since a
  skip often leaves too little running to measure.

All grouping happens in Python, so it works the same on SQLite and PostgreSQL.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from runnify.extensions import db
from runnify.filters import lift_number, pace
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
MIN_PHASE_PLAYS = 30  # plays of repeated songs needed to judge a part of the run


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


def _weighted_mean(pairs):
    total_weight = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total_weight if total_weight else None


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


@dataclass
class Phase:
    """How songs did in one part of a run (the start, middle or finish)."""

    label: str
    plays: int
    lift: float | None  # weighted mean effect of the songs played there, s/km
    strength: float | None  # how strongly songs' usual effects showed up there (1 = as usual)


def _phase_of(position):
    position = position or 0.0
    return next((label for label, low, high in PHASES if low <= position < high), PHASES[-1][0])


def _slope(points):
    """Weighted least-squares slope of ``(x, y, weight)`` points (``None`` if undefined)."""
    if len(points) < MIN_PHASE_PLAYS:
        return None
    total = sum(w for *_, w in points)
    mean_x = sum(x * w for x, _, w in points) / total
    mean_y = sum(y * w for _, y, w in points) / total
    spread = sum(w * (x - mean_x) ** 2 for x, _, w in points)
    if spread <= 0:
        return None
    return sum(w * (x - mean_x) * (y - mean_y) for x, y, w in points) / spread


def phase_summary(plays):
    """Summarise ``(song_key, position, pace_delta, seconds)`` plays by part of the run.

    ``strength`` answers "does my choice of song matter more at the start or at
    the finish?". Each play is set against the same song's average over its
    other plays, and the slope of that relationship within one part of the run
    says how strongly songs worked there: 1 is as usual, 1.5 is half as much
    again, 0.5 is half as much. A slope ignores anything that shifts every song
    alike, such as a slow warm-up, which skews the plain average (``lift``).
    """
    plays = [
        (key, position, delta, max(seconds or 0, 1)) for key, position, delta, seconds in plays
    ]
    songs = defaultdict(lambda: [0.0, 0.0, 0])  # key -> [weighted delta sum, weight, plays]
    for key, _position, delta, weight in plays:
        song = songs[key]
        song[0] += delta * weight
        song[1] += weight
        song[2] += 1

    effects = {label: [] for label, _, _ in PHASES}  # label -> [(delta, weight)]
    points = {label: [] for label, _, _ in PHASES}  # label -> [(usual effect, delta, weight)]
    for key, position, delta, weight in plays:
        label = _phase_of(position)
        effects[label].append((delta, weight))
        total, total_weight, count = songs[key]
        if count >= MIN_PLAYS_TO_RANK:
            usual = (total - delta * weight) / (total_weight - weight)  # leave this play out
            points[label].append((usual, delta, weight))
    return [
        Phase(label, len(effects[label]), _weighted_mean(effects[label]), _slope(points[label]))
        for label, _, _ in PHASES
    ]


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


def aggregate(rows, key_of, label_of, detail_of=lambda song: ""):
    """Group scored plays into :class:`Effect` objects.

    Args:
        rows: ``(analysis, play, song, run)`` tuples; only ``analysis.pace_delta``,
            ``.hr_delta`` and ``.seconds`` and ``run.id`` are read.
        key_of: Groups a song (return ``None`` to leave it out).
        label_of, detail_of: Text for the group.
    """
    groups = {}
    hr_weights = defaultdict(lambda: [0.0, 0.0])  # key -> [weighted hr sum, weight]
    for analysis, _play, song, run in rows:
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
        effect.runs.add(run.id)
        if analysis.hr_delta is not None:
            hr_weights[key][0] += analysis.hr_delta * weight
            hr_weights[key][1] += weight
    for key, (total, weight) in hr_weights.items():
        groups[key].hr_delta = total / weight if weight else None
    return list(groups.values())


def song_effects(user_id, since=None):
    """Every scored song for ``user_id`` (optionally only runs since ``since``)."""
    return aggregate(
        _rows(user_id, since),
        key_of=lambda song: song.id,
        label_of=lambda song: song.name or "Unknown track",
        detail_of=lambda song: song.artist or "",
    )


def artist_effects(user_id, since=None):
    """Every artist with scored plays for ``user_id``."""
    return aggregate(
        _rows(user_id, since),
        key_of=lambda song: (song.artist or "").strip() or None,
        label_of=lambda song: song.artist,
    )


def ranked(effects, best=True, limit=5):
    """The strongest lifts (``best``) or drags with enough evidence, by shrunk effect."""
    pool = [e for e in effects if e.plays >= MIN_PLAYS_TO_RANK]
    pool = [e for e in pool if (e.shrunk_lift > 0 if best else e.shrunk_lift < 0)]
    return sorted(pool, key=lambda e: e.shrunk_lift, reverse=best)[:limit]


def heart_raisers(effects, limit=5):
    """Songs with enough evidence that raised heart rate, the biggest rise first."""
    pool = [e for e in effects if e.plays >= MIN_PLAYS_TO_RANK and (e.hr_delta or 0) > 0]
    return sorted(pool, key=lambda e: e.hr_delta, reverse=True)[:limit]


@dataclass
class SkipCount:
    """How often the runner skipped one song during their runs.

    Unlike an :class:`Effect`, it counts every play, measured or not, as the
    song's page does: a skip often leaves too little running to measure, so
    the measured plays alone would miss it.
    """

    key: str
    label: str
    detail: str = ""
    heard: int = 0  # plays during runs, measured or not
    skips: int = 0
    runs: set = field(default_factory=set)  # runs it played in, measured or not


def _all_plays(user_id, since=None):
    """Every play during ``user_id``'s runs, measured or not, as ``(play, song, run)`` tuples."""
    query = (
        db.session.query(UserSongHistory, Song, Run)
        .join(Song, Song.id == UserSongHistory.song_id)
        .join(Run, Run.id == UserSongHistory.run_id)
        .filter(UserSongHistory.user_id == user_id, Run.user_id == user_id)
    )
    if since is not None:
        query = query.filter(Run.date_time >= since)
    return query.all()


def skip_counts(user_id, since=None):
    """A :class:`SkipCount` for every song ``user_id`` heard during runs since ``since``."""
    counts = {}
    for play, song, run in _all_plays(user_id, since):
        count = counts.setdefault(
            song.id,
            SkipCount(key=song.id, label=song.name or "Unknown track", detail=song.artist or ""),
        )
        count.heard += 1
        count.skips += bool(play.skipped)
        count.runs.add(run.id)
    return list(counts.values())


def most_skipped(counts, limit=5):
    """Songs skipped most often during runs, the more often heard first on a tie."""
    return sorted((c for c in counts if c.skips), key=lambda c: (c.skips, c.heard), reverse=True)[
        :limit
    ]


@dataclass
class Overview:
    """Everything the Insights page shows for one date range."""

    range_key: str
    range_label: str
    plays: int
    songs: int
    runs_with_music: int
    music_seconds: int
    power_songs: list
    drag_songs: list
    top_artists: list
    phases: list  # Phase for the start, middle and finish
    heart_raisers: list
    most_skipped: list  # SkipCount, over every play in the range
    with_music_pace: float | None
    without_music_pace: float | None

    @property
    def has_data(self):
        return self.plays > 0


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
    songs = aggregate(
        rows, lambda s: s.id, lambda s: s.name or "Unknown track", lambda s: s.artist or ""
    )
    artists = aggregate(rows, lambda s: (s.artist or "").strip() or None, lambda s: s.artist)

    with_music, without_music = _run_paces(user_id, since)
    return Overview(
        range_key=range_key,
        range_label=RANGES[range_key][0],
        plays=len(rows),
        songs=len(songs),
        runs_with_music=len({run.id for *_, run in rows}),
        music_seconds=sum(analysis.seconds or 0 for analysis, *_ in rows),
        power_songs=ranked(songs, best=True),
        drag_songs=ranked(songs, best=False),
        top_artists=ranked(artists, best=True),
        phases=phase_summary(
            (song.id, a.position, a.pace_delta, a.seconds) for a, _, song, _ in rows
        ),
        heart_raisers=heart_raisers(songs),
        most_skipped=most_skipped(skip_counts(user_id, since)),
        with_music_pace=with_music,
        without_music_pace=without_music,
    )


@dataclass
class Highlight:
    """One finding written as a sentence, for the dashboard and the Insights page.

    Reads as ``lead`` (in bold, often a song) then ``text``. ``figure`` and
    ``unit`` are the number it rests on and ``foot`` the evidence behind it.
    ``kind`` picks its colour: "lift", "drag", "heart", "pace" or "music".
    ``song_id`` is set when the lead is a song, so it can link to the song's page.
    """

    kind: str
    kicker: str
    icon: str
    lead: str
    text: str
    figure: str
    unit: str
    foot: str
    song_id: str | None = None


def _evidence(effect):
    runs = len(effect.runs)
    return f"{runs} run{'' if runs == 1 else 's'}, {effect.plays} play{'' if effect.plays == 1 else 's'}"


def highlights(overview):
    """Plain-language findings from an :class:`Overview`, the strongest evidence first.

    Every sentence is worked out from the numbers on the page (nothing is
    generated), and each carries the runs and plays it rests on.
    """
    found = []
    if overview.power_songs:
        top = overview.power_songs[0]
        found.append(
            Highlight(
                "lift",
                "Power song",
                "trend-up",
                top.label,
                "lifts your pace more reliably than any other song.",
                lift_number(top.shrunk_lift),
                "s/km faster",
                _evidence(top),
                song_id=top.key,
            )
        )
    if overview.drag_songs:
        worst = overview.drag_songs[0]
        found.append(
            Highlight(
                "drag",
                "Drag song",
                "trend-down",
                worst.label,
                "slows you down the most. Save it for the cool-down.",
                lift_number(worst.shrunk_lift),
                "s/km slower",
                _evidence(worst),
                song_id=worst.key,
            )
        )
    measured = [phase for phase in overview.phases if phase.strength is not None]
    if len(measured) >= 2:
        strongest = max(measured, key=lambda phase: phase.strength)
        found.append(
            Highlight(
                "pace",
                "Where music works",
                "gauge",
                f"The {strongest.label.lower()}",
                "of a run is where your songs work hardest.",
                f"{strongest.strength:.1f}\u00d7",
                "as strongly as usual",
                f"{strongest.plays} plays in that part of your runs",
            )
        )
    if overview.heart_raisers:
        raiser = overview.heart_raisers[0]
        found.append(
            Highlight(
                "heart",
                "Heart raiser",
                "heart",
                raiser.label,
                "pushes your heart rate up the most. Easy-run playlists rank it lower.",
                lift_number(raiser.hr_delta),
                "bpm",
                _evidence(raiser),
                song_id=raiser.key,
            )
        )
    if overview.with_music_pace and overview.without_music_pace:
        gap = round(overview.without_music_pace - overview.with_music_pace)
        if gap:
            direction = "faster" if gap > 0 else "slower"
            text = f"averaged {abs(gap)} s/km {direction} than runs without."
        else:
            text = "averaged the same pace as runs without."
        found.append(
            Highlight(
                "music",
                "With music",
                "headphones",
                "Runs with music",
                text,
                pace(overview.with_music_pace),
                "/km",
                "A rough guide: you may run different sessions with and without music.",
            )
        )
    if overview.most_skipped:
        skipped = overview.most_skipped[0]
        found.append(
            Highlight(
                "music",
                "Most skipped",
                "skip",
                skipped.label,
                "is the song you skip most often mid-run.",
                str(skipped.skips),
                f"of {skipped.heard} play{'' if skipped.heard == 1 else 's'}",
                f"{len(skipped.runs)} run{'' if len(skipped.runs) == 1 else 's'}",
                song_id=skipped.key,
            )
        )
    return found
