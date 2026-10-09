"""A run's results sheet: every song that played, ranked by how it changed the pace.

Effects come from the stored analysis (see :mod:`runnify.services.analysis`),
so a page shows exactly what the insights and playlists were built from.
"""

from dataclasses import dataclass, field

from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory
from runnify.services.analysis import song_segments
from runnify.services.fit import Series
from runnify.services.streams import load_series


@dataclass
class ResultRow:
    """One song play during a run."""

    play: UserSongHistory
    song: Song
    start: int  # seconds into the run when the song came on
    seconds: int  # seconds of the song inside the run
    lift: float | None = None  # s/km faster (+) or slower (-) than the minutes around it
    hr_delta: float | None = None  # bpm above (+) or below (-) the minutes around it
    position: int | None = None  # rank among the scored songs, 1 = the biggest lift
    kind: str = "normal"  # "best", "worst" or "normal"

    @property
    def scored(self):
        return self.lift is not None

    @property
    def note(self):
        """Why an unscored play has no result."""
        if self.scored:
            return None
        if self.play.skipped:
            return "Skipped"
        return "Too little running during the song to measure"


@dataclass
class RunResults:
    run: Run
    series: Series
    rows: list[ResultRow] = field(default_factory=list)  # in playing order

    @property
    def ranked(self):
        return sorted((r for r in self.rows if r.scored), key=lambda r: r.lift, reverse=True)

    @property
    def unscored(self):
        return [r for r in self.rows if not r.scored]

    @property
    def best(self):
        return next((r for r in self.rows if r.kind == "best"), None)

    @property
    def worst(self):
        return next((r for r in self.rows if r.kind == "worst"), None)

    def bands(self):
        """``(start, end, label, kind)`` for each play, for :func:`charts.run_chart`."""
        return [
            (r.start, r.start + r.seconds, r.song.name or "Unknown track", r.kind)
            for r in self.rows
        ]


def run_results(run, series=None):
    """Build ``run``'s results sheet from its stream and stored song effects."""
    series = series if series is not None else load_series(run)
    effects = {a.user_song_id: a for a in RunSongAnalysis.query.filter_by(run_id=run.id)}
    results = RunResults(run=run, series=series)
    if not len(series):
        return results
    first = series.timestamps[0]
    for play, song, start, end in song_segments(run, series):
        effect = effects.get(play.id)
        results.rows.append(
            ResultRow(
                play=play,
                song=song,
                start=int((start - first).total_seconds()),
                seconds=int((end - start).total_seconds()),
                lift=effect.pace_delta if effect else None,
                hr_delta=effect.hr_delta if effect else None,
            )
        )
    ranked = results.ranked
    for position, row in enumerate(ranked, start=1):
        row.position = position
    if ranked and ranked[0].lift > 0:
        ranked[0].kind = "best"
    if len(ranked) > 1 and ranked[-1].lift < 0:
        ranked[-1].kind = "worst"
    return results


@dataclass
class RunSummary:
    """What the runs list shows about a run's music."""

    songs: int = 0  # songs that played during the run
    best: Song | None = None  # the song with the biggest lift
    best_lift: float | None = None


def run_summaries(run_ids):
    """Songs played and the best song for each of ``run_ids``, in two queries."""
    summaries = {run_id: RunSummary() for run_id in run_ids}
    if not summaries:
        return summaries
    counts = (
        db.session.query(UserSongHistory.run_id, db.func.count(UserSongHistory.id))
        .filter(UserSongHistory.run_id.in_(summaries))
        .group_by(UserSongHistory.run_id)
    )
    for run_id, count in counts:
        summaries[run_id].songs = count
    effects = (
        db.session.query(RunSongAnalysis.run_id, RunSongAnalysis.pace_delta, Song)
        .join(UserSongHistory, UserSongHistory.id == RunSongAnalysis.user_song_id)
        .join(Song, Song.id == UserSongHistory.song_id)
        .filter(RunSongAnalysis.run_id.in_(summaries), RunSongAnalysis.pace_delta.isnot(None))
    )
    for run_id, lift, song in effects:
        summary = summaries[run_id]
        if summary.best_lift is None or lift > summary.best_lift:
            summary.best, summary.best_lift = song, lift
    return summaries
