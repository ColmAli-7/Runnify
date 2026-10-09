"""Sample results for the public landing page, computed by the real engine.

Nothing here is typed in by hand: a few runs are simulated with the demo
simulator, every song is scored with the real scoring method, and the findings
come from the same insights and playlist code that real accounts use. The
landing page labels all of it as sample data. Computed once per process.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from types import SimpleNamespace

from runnify.filters import NBSP, lift_number, plural
from runnify.services import charts, insights
from runnify.services.demo import SONGS, _simulate
from runnify.services.playlists import PlannedTrack, arrange
from runnify.services.scoring import song_effect

FEATURED_START = datetime(2026, 9, 29, 7, 4)
OTHER_RUNS = ("easy", "tempo", "long", "easy", "tempo", "easy")
PLAYLIST_MINUTES = 30


@dataclass(frozen=True)
class SampleSong:
    name: str
    artist: str


@dataclass
class SampleRow:
    """One song in the featured run's results."""

    position: int
    song: SampleSong
    at_second: int
    seconds: int
    lift: float


@dataclass
class Sample:
    """Everything the landing page shows."""

    run_label: str
    run_date: datetime
    distance_m: float
    duration_s: int
    avg_hr: int
    rows: list[SampleRow]
    chart: charts.RunChart
    stage_charts: dict = field(default_factory=dict)
    power: list = field(default_factory=list)  # insights.Effect, strongest first
    drag: list = field(default_factory=list)
    heart: list = field(default_factory=list)  # songs that raised heart rate most
    playlist: list = field(default_factory=list)  # (PlannedTrack, start second)
    ramp: charts.BarChart = field(default_factory=charts.BarChart)  # the playlist's lifts in order
    runs_simulated: int = 0

    @property
    def best(self):
        return self.rows[0]

    @property
    def worst(self):
        return self.rows[-1]

    @property
    def findings(self):
        """Plain-language findings for the landing page, as ``(mark, song, rest)``.

        A finding reads ``song`` then ``rest``. ``mark`` says how the song name is
        drawn: "power" (highlighter), "drag" (red pen) or ``None``. A finding that
        doesn't start with a song has ``song`` set to ``None``.
        """
        top, drag, heart = self.power[0], self.drag[0], self.heart[0]
        first, last = self.playlist[0][0], self.playlist[-1][0]
        return [
            (
                "power",
                top.label,
                f"lifted the pace by {_amount(top.shrunk_lift)} across {_runs(top)}.",
            ),
            (
                "drag",
                drag.label,
                f"slowed the pace by {_amount(drag.shrunk_lift)} across {_runs(drag)}. "
                "Keep it for the cool-down.",
            ),
            (
                None,
                heart.label,
                f"raised heart rate the most: {round(heart.hr_delta)}{NBSP}bpm "
                "above the minutes around it.",
            ),
            (
                None,
                None,
                f"A {PLAYLIST_MINUTES}-minute tempo playlist built from these results starts with "
                f"{first.song.name} and finishes with {last.song.name}.",
            ),
        ]


def _amount(seconds_per_km):
    return f"{abs(round(seconds_per_km))}{NBSP}s/km"


def _runs(effect):
    return plural(len(effect.runs), "run")


def _run(rng, start, kind, songs):
    """Simulate and score one run: ``(series, plays, metres, seconds, average_hr)``."""
    series, plays, metres, seconds, avg_hr = _simulate(rng, start, kind, songs)
    measured = []
    for song, song_start, length, skipped in plays:
        effect = song_effect(
            series,
            start + timedelta(seconds=song_start),
            start + timedelta(seconds=song_start + length),
        )
        measured.append((song, song_start, length, skipped, effect))
    return series, measured, metres, seconds, avg_hr


def _rows_for_insights(run_id, measured):
    """Scored plays shaped like the rows :func:`insights.aggregate` reads from the database."""
    return [
        (effect, SimpleNamespace(skipped=skipped), song, SimpleNamespace(id=run_id))
        for song, _start, _length, skipped, effect in measured
        if effect.pace_delta is not None
    ]


@lru_cache(maxsize=1)
def landing_sample():
    """Simulate and score the sample once; see the module docstring."""
    rng = random.Random(316)  # noqa: S311  (a repeatable illustration, not security)
    songs = [
        (SampleSong(title, artist), length, effect, hr)
        for title, artist, length, effect, hr in SONGS
    ]
    lengths = {song: length for song, length, *_ in songs}

    # the featured run: a tempo run on a fixed morning
    series, measured, metres, seconds, avg_hr = _run(rng, FEATURED_START, "tempo", songs)
    scored = sorted(
        (m for m in measured if m[4].score is not None and not m[3]),
        key=lambda m: m[4].pace_delta,
        reverse=True,
    )
    rows = [
        SampleRow(i + 1, song, song_start, length, effect.pace_delta)
        for i, (song, song_start, length, _skipped, effect) in enumerate(scored)
    ]
    best, worst = scored[0][0], scored[-1][0]
    bands = [
        (
            start,
            start + length,
            song.name,
            "best" if song == best else "worst" if song == worst else "normal",
        )
        for song, start, length, _skipped, _effect in measured
    ]

    # three stages of "how a song is measured", on the same run
    _, best_start, best_length, _, _ = scored[0]
    stage_charts = {
        "pace": charts.run_chart(series.paces),
        "context": charts.run_chart(
            series.paces,
            [
                (max(best_start - 300, 0), best_start, "5 minutes before", "context"),
                (best_start, best_start + best_length, best.name, "best"),
                (
                    best_start + best_length,
                    best_start + best_length + 300,
                    "5 minutes after",
                    "context",
                ),
            ],
        ),
    }

    # findings across the featured run and a few more, from the real insights code
    plays = _rows_for_insights(0, measured)
    for n, kind in enumerate(OTHER_RUNS, start=1):
        _, others, *_ = _run(rng, FEATURED_START - timedelta(days=3 * n), kind, songs)
        plays += _rows_for_insights(n, others)
    effects = insights.aggregate(
        plays, key_of=lambda s: s, label_of=lambda s: s.name, detail_of=lambda s: s.artist
    )

    # a playlist chosen and ordered the way the playlist builder does it for a tempo run
    chosen, used = [], 0
    for effect in insights.ranked(effects, best=True, limit=len(effects)):
        if used >= PLAYLIST_MINUTES * 60:
            break
        chosen.append(
            PlannedTrack(
                effect.key, lengths[effect.key], round(effect.shrunk_lift, 1), effect.plays
            )
        )
        used += lengths[effect.key]
    playlist, clock = [], 0
    for track in arrange("tempo", chosen):
        playlist.append((track, clock))
        clock += track.seconds

    return Sample(
        run_label="Tempo run",
        run_date=FEATURED_START,
        distance_m=metres,
        duration_s=seconds,
        avg_hr=avg_hr,
        rows=rows,
        chart=charts.run_chart(series.paces, bands),
        stage_charts=stage_charts,
        power=insights.ranked(effects, best=True, limit=3),
        drag=insights.ranked(effects, best=False, limit=2),
        heart=insights.heart_raisers(effects, limit=3),
        playlist=playlist,
        ramp=charts.bar_chart(
            [(str(i), track.lift) for i, (track, _) in enumerate(playlist, start=1)],
            value_format=lift_number,
        ),
        runs_simulated=1 + len(OTHER_RUNS),
    )
