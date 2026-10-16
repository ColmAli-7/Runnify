"""One song across a runner's runs: its lift, every play and the trend (the song page).

Songs are shared rows but plays are each runner's own, so a song is only ever
looked up through the runner's plays: one they never heard on a run has no
page for them. The lift and its evidence are the same aggregate the Insights
page ranks on (:mod:`runnify.services.insights`), taken over all time.

A trend line is drawn through the measured plays once there are enough of them
on different days, but the page only calls it a trend when the line is too
steep to put down to the ups and downs of the plays themselves.
"""

import math
from dataclasses import dataclass

from sqlalchemy import and_

from runnify import filters
from runnify.extensions import db
from runnify.models import Run, RunSongAnalysis, Song, UserSongHistory
from runnify.services import charts
from runnify.services.insights import MIN_PLAYS_TO_RANK, Effect, ranked, song_effects

MIN_TREND_PLAYS = 3  # measured plays, on two days or more, before a trend line is drawn
CLEAR_TREND = 3.0  # standard errors from level before the page calls the line a trend
MIN_CLEAR_TREND_PLAYS = 8  # and never on fewer measured plays than this
TOP_SONGS = 5  # as many as the Insights page lists as power or drag songs


@dataclass
class SongPlay:
    """One play of the song during one of the runner's runs."""

    play: UserSongHistory
    run: Run
    analysis: RunSongAnalysis | None = None  # None when the play couldn't be measured

    @property
    def lift(self):
        """s/km faster (+) or slower (-) than the minutes around it, or ``None``."""
        return None if self.analysis is None else self.analysis.pace_delta

    @property
    def hr_delta(self):
        """bpm above (+) or below (-) the minutes around it, or ``None``."""
        return None if self.analysis is None else self.analysis.hr_delta

    @property
    def scored(self):
        return self.lift is not None

    @property
    def on_at(self):
        """Seconds into the run when the song came on."""
        if self.play.played_at is None or self.run.date_time is None:
            return None
        return max(int((self.play.played_at - self.run.date_time).total_seconds()), 0)


@dataclass
class Trend:
    """A straight line through a song's measured plays over time."""

    first: float  # the line's lift on the first play's date, s/km
    last: float  # the line's lift on the last play's date, s/km
    per_day: float  # how much the lift changes each day, s/km
    clear: bool  # too steep to put down to chance


def fit_trend(points):
    """Fit a trend line through ``(day, lift, weight)`` points.

    ``day`` is any day number (such as ``date.toordinal()``) and ``weight`` the
    seconds measured, as for the song's lift, so the line passes through the
    lift at the plays' average date. ``clear`` needs ``MIN_CLEAR_TREND_PLAYS``
    plays and a slope ``CLEAR_TREND`` standard errors from level: the plays'
    own ups and downs produce that by chance less than one time in forty.

    Returns:
        A :class:`Trend`, or ``None`` with fewer than ``MIN_TREND_PLAYS`` plays
        or every play on the same day.
    """
    if len(points) < MIN_TREND_PLAYS:
        return None
    total = sum(weight for *_, weight in points)
    mean_x = sum(x * weight for x, _, weight in points) / total
    mean_y = sum(y * weight for _, y, weight in points) / total
    spread = sum(weight * (x - mean_x) ** 2 for x, _, weight in points)
    if spread <= 0:
        return None
    slope = sum(weight * (x - mean_x) * (y - mean_y) for x, y, weight in points) / spread
    misfit = sum(weight * (y - mean_y - slope * (x - mean_x)) ** 2 for x, y, weight in points)
    error = math.sqrt(misfit / (len(points) - 2) / spread)
    days = [x for x, _, _ in points]
    return Trend(
        first=mean_y + slope * (min(days) - mean_x),
        last=mean_y + slope * (max(days) - mean_x),
        per_day=slope,
        clear=len(points) >= MIN_CLEAR_TREND_PLAYS and abs(slope) > CLEAR_TREND * error,
    )


@dataclass
class SongRecord:
    """Everything a song's page shows for one runner."""

    song: Song
    plays: list[SongPlay]  # every play during their runs, newest first
    effect: Effect  # lift and evidence over all time, exactly as Insights ranks it
    rank: int | None  # among songs that lift (or drag) the runner; None when it doesn't rank
    ranked_songs: int  # how many songs rank on the same side
    trend: Trend | None

    @property
    def name(self):
        return self.song.name or "Unknown track"

    @property
    def measured(self):
        """The plays with a lift, oldest first."""
        return [play for play in reversed(self.plays) if play.scored]

    @property
    def runs(self):
        """How many runs it played in, measured or not."""
        return len({play.run.id for play in self.plays})

    @property
    def skips(self):
        """Plays the runner skipped, measured or not."""
        return sum(bool(play.play.skipped) for play in self.plays)

    @property
    def plays_to_rank(self):
        """Measured plays it still needs before it can rank (0 once it ranks)."""
        return max(MIN_PLAYS_TO_RANK - self.effect.plays, 0)


def song_record(user_id, song_id):
    """``user_id``'s record of one song, or ``None`` if they never heard it during a run."""
    rows = (
        db.session.query(UserSongHistory, Run, RunSongAnalysis)
        .join(Run, Run.id == UserSongHistory.run_id)
        .outerjoin(
            RunSongAnalysis,
            and_(
                RunSongAnalysis.user_song_id == UserSongHistory.id,
                RunSongAnalysis.pace_delta.isnot(None),
            ),
        )
        .filter(
            UserSongHistory.user_id == user_id,
            UserSongHistory.song_id == song_id,
            Run.user_id == user_id,
        )
        .order_by(Run.date_time.desc(), UserSongHistory.played_at.desc())
        .all()
    )
    if not rows:
        return None
    song = db.session.get(Song, song_id)
    plays = [SongPlay(play, run, analysis) for play, run, analysis in rows]

    effects = song_effects(user_id)
    effect = next((e for e in effects if e.key == song.id), None) or Effect(
        key=song.id, label=song.name or "Unknown track", detail=song.artist or ""
    )
    rank, side = None, []
    if effect.plays >= MIN_PLAYS_TO_RANK and filters.lift_kind(effect.shrunk_lift) != "flat":
        side = [
            e
            for e in ranked(effects, best=effect.shrunk_lift > 0, limit=None)
            if filters.lift_kind(e.shrunk_lift) != "flat"  # under 1 s/km is "little effect"
        ]
        rank = next(position for position, e in enumerate(side, 1) if e.key == song.id)

    record = SongRecord(song, plays, effect, rank, ranked_songs=len(side), trend=None)
    record.trend = fit_trend(
        [
            (play.run.local_start.toordinal(), play.lift, max(play.analysis.seconds or 0, 1))
            for play in record.measured
        ]
    )
    return record


@dataclass
class Verdict:
    """The sentence at the top of a song's page: ``lead`` in bold, then ``text``."""

    lead: str
    text: str


def _compared(lift):
    """``12.4`` -> ``"12 s/km faster than"``; near zero, ``"about the same pace as"``."""
    kind = filters.lift_kind(lift)
    if kind == "flat":
        return "about the same pace as"
    return f"{abs(round(lift))}{filters.NBSP}s/km {'faster' if kind == 'up' else 'slower'} than"


def verdict(record):
    """What the song does for the runner, in plain words worked out from its numbers.

    A song that can't rank yet says how much more evidence it needs.
    """
    effect = record.effect
    if record.plays_to_rank:
        if effect.plays == 1:
            found = f"Its one measured play was {_compared(effect.lift)} the minutes around it."
        elif effect.plays:
            found = (
                f"Its {effect.plays} measured plays averaged {_compared(effect.lift)} "
                "the minutes around them."
            )
        elif all(play.play.skipped for play in record.plays):
            found = "You skipped it before it could be measured."
        else:
            found = "It didn't play for long enough while you were running to be measured."
        needed = filters.plural(
            record.plays_to_rank, "more measured play" if effect.plays else "measured play"
        )
        return Verdict("Not ranked yet.", f"{found} It needs {needed} before it can rank.")

    kind = filters.lift_kind(effect.shrunk_lift)
    runs = filters.plural(len(effect.runs), "run")
    if kind == "flat":
        lead = "Little effect on your pace."
        text = f"Its lift is under 1{filters.NBSP}s/km either way across {runs}."
    else:
        amount = f"{abs(round(effect.shrunk_lift))}{filters.NBSP}s/km"
        faster = kind == "up"
        text = f"It {'lifts your pace' if faster else 'slows you down'} by {amount} across {runs}"
        if record.rank > TOP_SONGS:
            lead = "A smaller lift." if faster else "A smaller drag."
            text += f", {filters.ordinal(record.rank)} of the {record.ranked_songs} songs that do."
        else:
            place = "Your" if record.rank == 1 else f"Your {filters.ordinal(record.rank)}"
            lead = f"{place} {'strongest song' if faster else 'biggest drag'}."
            text += "." if faster else ". Save it for the cool-down."
    trend = record.trend
    if trend is not None and trend.clear:
        text += (
            f" Its lift has {'risen' if trend.per_day > 0 else 'fallen'} on recent runs,"
            f" from {filters.lift_number(trend.first)} to {filters.lift(trend.last)}."
        )
    return Verdict(lead, text)


def trend_note(record):
    """What the trend line shows, under the chart and in its written summary."""
    trend = record.trend
    if trend is None:
        return (
            f"A trend line appears once it has {MIN_TREND_PLAYS} measured plays on different days."
        )
    first, last = filters.lift_number(trend.first), filters.lift(trend.last)
    if first == filters.lift_number(trend.last):
        return f"The trend line is level at {last}."
    direction = "rises" if trend.last > trend.first else "falls"
    line = f"The trend line {direction} from {first} to {last}"
    if trend.clear:
        return f"{line}, more than the ups and downs of its plays would explain."
    return f"{line}, but its plays vary too much to call that a trend yet."


def chart(record):
    """The matched-runs chart: a dot per measured play by run date, and the trend line."""
    trend = record.trend
    return charts.matched_chart(
        (
            (
                play.run.local_start,
                play.lift,
                f"{filters.day(play.run.local_start)}, {filters.run_name(play.run.local_start)}: "
                f"{filters.lift(play.lift)}",
            )
            for play in record.measured
        ),
        trend=None if trend is None else (trend.first, trend.last),
    )


def chart_summary(record):
    """A written account of the chart, for anyone who can't see it."""
    measured = record.measured
    if not measured:
        return ""
    kinds = [filters.lift_kind(play.lift) for play in measured]
    tallies = [
        (kinds.count(kind), word)
        for kind, word in (("up", "faster"), ("down", "slower"), ("flat", "about the same"))
        if kind in kinds
    ]
    parts = [f"{count} {word}" for count, word in tallies]
    parts[0] = f"{tallies[0][0]} {'was' if tallies[0][0] == 1 else 'were'} {tallies[0][1]}"
    listed = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    first, last = measured[0].run.local_start, measured[-1].run.local_start
    when = (
        f"on {filters.day(first)}"
        if first.date() == last.date()
        else f"from {filters.day(first)} to {filters.day(last)}"
    )
    around = "it" if len(measured) == 1 else "them"
    return (
        f"{filters.plural(len(measured), 'measured play')} of {record.name} by run date, {when}. "
        f"Compared with the minutes around {around}, {listed}. {trend_note(record)}"
    )
