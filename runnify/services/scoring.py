"""How much a song changed the runner's pace: the per-song "effect".

Each song is compared with the runner's own pace in the minutes either side of
it in the same run, not with the whole run's average. A whole-run average
treats warm-ups, hills and late surges as if they were the music's doing;
local context mostly cancels them out. All statistics are robust (medians and
the median absolute deviation), so a GPS wobble can't swing a score, and
samples where the runner was stopped carry no pace and are ignored.

The score keeps its familiar scale: 50 means "your usual pace at that point in
the run", every robust standard deviation faster adds 20 points, clamped to
0-100. ``pace_delta`` gives the same effect in seconds per km, which is easier
to read ("11 s/km faster").
"""

from dataclasses import dataclass
from datetime import timedelta
from statistics import median

METHOD_VERSION = 2
CONTEXT = timedelta(minutes=5)  # how far either side of a song its baseline looks
MIN_SONG_SAMPLES = 20  # roughly 20 seconds of moving time
MIN_CONTEXT_SAMPLES = 30
MIN_SPREAD = 5.0  # s/km; floor for the robust spread so steady runs don't exaggerate scores
MAD_TO_SD = 1.4826  # scales a median absolute deviation to a standard deviation


@dataclass
class SongEffect:
    """The measured effect of one song segment within one run."""

    score: float | None  # 0-100; 50 = your usual pace at that point; None = not enough data
    pace_delta: float | None  # s/km faster (+) or slower (-) than the surrounding baseline
    hr_delta: float | None  # bpm above (+) or below (-) the surrounding baseline
    seconds: int  # seconds of moving samples inside the segment
    position: float  # where in the run the segment started, 0 (start) to 1 (finish)


def _robust_spread(values):
    centre = median(values)
    return MAD_TO_SD * median(abs(v - centre) for v in values)


def song_effect(series, start, end):
    """Measure how ``series`` changed between ``start`` and ``end`` relative to its surroundings.

    Args:
        series: The run's :class:`~runnify.services.fit.Series`.
        start, end: The song segment (naive UTC datetimes, already trimmed to the run).

    Returns:
        A :class:`SongEffect`; its ``score`` is ``None`` when the segment or its
        surroundings have too few moving samples to judge.
    """
    timestamps, paces, heart_rates = series.timestamps, series.paces, series.heart_rates
    if not timestamps:
        return SongEffect(None, None, None, 0, 0.0)
    run_start, run_end = timestamps[0], timestamps[-1]
    duration = (run_end - run_start).total_seconds() or 1.0
    position = min(max((start - run_start).total_seconds() / duration, 0.0), 1.0)

    inside = [i for i, t in enumerate(timestamps) if start <= t <= end]
    near = [
        i
        for i, t in enumerate(timestamps)
        if (start - CONTEXT <= t < start) or (end < t <= end + CONTEXT)
    ]
    song_paces = [paces[i] for i in inside if paces[i] is not None]
    if len(song_paces) < MIN_SONG_SAMPLES:
        return SongEffect(None, None, None, len(song_paces), round(position, 3))

    context_paces = [paces[i] for i in near if paces[i] is not None]
    # e.g. a song at the very start: use the rest of the run
    if len(context_paces) < MIN_CONTEXT_SAMPLES:
        inside_set = set(inside)
        near = [i for i in range(len(timestamps)) if i not in inside_set]
        context_paces = [paces[i] for i in near if paces[i] is not None]
        if len(context_paces) < MIN_CONTEXT_SAMPLES:
            return SongEffect(None, None, None, len(song_paces), round(position, 3))

    all_paces = [p for p in paces if p is not None]
    spread = max(_robust_spread(all_paces), MIN_SPREAD)
    pace_delta = median(context_paces) - median(song_paces)  # positive = faster during the song
    score = max(0.0, min(100.0, 50 + 20 * pace_delta / spread))

    song_hr = [heart_rates[i] for i in inside if heart_rates[i] is not None]
    context_hr = [heart_rates[i] for i in near if heart_rates[i] is not None]
    hr_delta = median(song_hr) - median(context_hr) if song_hr and context_hr else None

    return SongEffect(
        score=round(score, 1),
        pace_delta=round(pace_delta, 1),
        hr_delta=None if hr_delta is None else round(hr_delta, 1),
        seconds=len(song_paces),
        position=round(position, 3),
    )
