"""How much a song changed the runner's pace: the per-song "effect".

Each song is compared with the runner's own pace in the minutes either side of
it in the same run, not with the whole run's average. A whole-run average
treats warm-ups, hills and late surges as if they were the music's doing;
local context mostly cancels them out. All statistics are robust (medians and
the median absolute deviation), so a GPS wobble can't swing a score, and
samples where the runner was stopped carry no pace and are ignored.

**Like is compared with like.** When a run has laps (see
:mod:`runnify.services.laps`), a song is measured on its main kind of lap and
compared with the same kind around it: a song during a hard rep against the
other reps, one during a jog against the other jogs, widening to the rest of
the run's laps of that kind when there are too few nearby. Walks never count,
and the first and last ``EDGE`` seconds of each lap (the change of pace
itself) are left out.

**Extra effort is charged.** Running faster costs heart rate, about 2 to 3 bpm
for every 10 s/km. A song that lifts the pace keeps its lift when heart rate
rose by about that much, but any rise beyond what the extra speed explains
(past ``HR_ALLOWANCE`` for noise) comes off the lift, which never drops below
zero. The cost of speed comes from the run itself, ``pace / (heart rate -
RESTING_HR)`` s/km per bpm, capped at ``COST_CAP``. It applies on steady
running only, since inside reps and recoveries heart rate is still climbing or
falling; slower songs are left as measured, so hills aren't counted twice.
Heart rate is read ``HR_LAG`` seconds late, as it trails the effort, and
ignored where it matches the cadence (a wrist sensor locked onto the steps).

The score keeps its familiar scale: 50 means "your usual pace at that point in
the run", every robust standard deviation faster adds 20 points, clamped to
0-100. ``pace_delta`` gives the same effect in seconds per km, which is easier
to read ("11 s/km faster").
"""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from statistics import median

METHOD_VERSION = 3
CONTEXT = timedelta(minutes=5)  # how far either side of a song its baseline looks
MIN_SONG_SAMPLES = 20  # roughly 20 seconds of moving time
MIN_CONTEXT_SAMPLES = 30
MIN_SPREAD = 5.0  # s/km; floor for the robust spread so steady runs don't exaggerate scores
MAD_TO_SD = 1.4826  # scales a median absolute deviation to a standard deviation
EDGE = 10  # seconds at each end of a lap left out: the change of pace itself
HR_LAG = 20  # seconds heart rate trails a change of effort
RESTING_HR = 60  # bpm assumed at rest, for the heart-rate cost of speed
COST_CAP = 4.0  # s/km per bpm at most, so slow running doesn't magnify heart-rate noise
HR_ALLOWANCE = 2.0  # bpm of rise beyond the cost of speed forgiven as noise
CADENCE_LOCK = 3  # bpm from the cadence at which heart rate is taken to be the steps
CHARGED_KINDS = (None, "steady")  # where heart rate settles enough to charge extra effort


@dataclass
class SongEffect:
    """The measured effect of one song segment within one run."""

    score: float | None  # 0-100; 50 = your usual pace at that point; None = not enough data
    pace_delta: float | None  # the lift: s/km faster (+) or slower (-) than the running around it
    hr_delta: float | None  # bpm above (+) or below (-) the surrounding baseline
    seconds: int  # seconds of moving samples measured inside the segment
    position: float  # where in the run the segment started, 0 (start) to 1 (finish)
    lap_kind: str | None = None  # the kind of lap it was measured on, when the run has laps
    effort_charge: float | None = None  # s/km taken off for extra effort; None = heart rate unused


def _robust_spread(values):
    centre = median(values)
    return MAD_TO_SD * median(abs(v - centre) for v in values)


def usable_kinds(kinds):
    """Each second's kind of lap, or ``None`` for walks and the edges of each lap.

    Edges are where the kind changes; the start and end of the run are not edges.
    """
    usable = list(kinds)
    length = len(kinds)
    for i in range(length):
        if kinds[i] == "walk":
            usable[i] = None
        elif (i > 0 and kinds[i - 1] != kinds[i]) or (i + 1 < length and kinds[i + 1] != kinds[i]):
            for j in range(max(i - EDGE + 1, 0), min(i + EDGE, length)):
                if kinds[j] == kinds[i]:
                    usable[j] = None
    return usable


def _heart(series, indexes):
    """Heart rate ``HR_LAG`` seconds after each of ``indexes``, leaving out cadence lock."""
    heart_rates, cadences = series.heart_rates, series.cadences
    found = []
    for i in indexes:
        j = i + HR_LAG
        if j >= len(heart_rates) or heart_rates[j] is None:
            continue
        if (
            cadences
            and cadences[j] is not None
            and abs(heart_rates[j] - cadences[j]) <= CADENCE_LOCK
        ):
            continue
        found.append(heart_rates[j])
    return found


def effort_charge(pace_change, hr_delta, context_pace, context_hr):
    """The s/km to take off a lift of ``pace_change`` for heart rate beyond its usual cost.

    ``None`` when heart rate can't be weighed (missing, or the song didn't lift
    the pace). Never more than the lift itself.
    """
    if hr_delta is None or context_hr is None or pace_change <= 0:
        return None
    cost = min(context_pace / max(context_hr - RESTING_HR, 1), COST_CAP)  # s/km per bpm
    extra = hr_delta - pace_change / cost - HR_ALLOWANCE
    return min(max(extra, 0.0) * cost, pace_change)


def song_effect(series, start, end, kinds=None):
    """Measure how ``series`` changed between ``start`` and ``end`` relative to its surroundings.

    Args:
        series: The run's :class:`~runnify.services.fit.Series`.
        start, end: The song segment (naive UTC datetimes, already trimmed to the run).
        kinds: The kind of lap each second (:func:`runnify.services.laps.kinds_by_second`),
            or ``None`` to treat the run as one steady stretch.

    Returns:
        A :class:`SongEffect`; its ``score`` is ``None`` when the segment or its
        surroundings have too few moving samples to judge.
    """
    timestamps, paces = series.timestamps, series.paces
    if not timestamps:
        return SongEffect(None, None, None, 0, 0.0)
    run_start, run_end = timestamps[0], timestamps[-1]
    duration = (run_end - run_start).total_seconds() or 1.0
    position = round(min(max((start - run_start).total_seconds() / duration, 0.0), 1.0), 3)

    inside = [i for i, t in enumerate(timestamps) if start <= t <= end]
    near = [
        i
        for i, t in enumerate(timestamps)
        if (start - CONTEXT <= t < start) or (end < t <= end + CONTEXT)
    ]
    kind, alike = None, None
    if kinds is not None:
        usable = usable_kinds(kinds)
        found = Counter(usable[i] for i in inside if usable[i] is not None and paces[i] is not None)
        if not found:
            return SongEffect(None, None, None, 0, position)
        kind = found.most_common(1)[0][0]
        alike = [i for i, k in enumerate(usable) if k == kind]
        inside = [i for i in inside if usable[i] == kind]
        near = [i for i in near if usable[i] == kind]

    song_paces = [paces[i] for i in inside if paces[i] is not None]
    if len(song_paces) < MIN_SONG_SAMPLES:
        return SongEffect(None, None, None, len(song_paces), position, kind)

    context_paces = [paces[i] for i in near if paces[i] is not None]
    # too little alike running nearby (a song at the very start, say): use the rest of the run
    if len(context_paces) < MIN_CONTEXT_SAMPLES:
        span = {i for i, t in enumerate(timestamps) if start <= t <= end}
        rest = alike if alike is not None else range(len(timestamps))
        near = [i for i in rest if i not in span]
        context_paces = [paces[i] for i in near if paces[i] is not None]
        if len(context_paces) < MIN_CONTEXT_SAMPLES:
            return SongEffect(None, None, None, len(song_paces), position, kind)

    compared = [paces[i] for i in (alike if alike is not None else range(len(paces)))]
    spread = max(_robust_spread([p for p in compared if p is not None]), MIN_SPREAD)
    pace_change = median(context_paces) - median(song_paces)  # positive = faster during the song

    song_hr, context_hr = _heart(series, inside), _heart(series, near)
    hr_delta = median(song_hr) - median(context_hr) if song_hr and context_hr else None
    charge = None
    if kind in CHARGED_KINDS:
        charge = effort_charge(
            pace_change, hr_delta, median(context_paces), median(context_hr) if context_hr else None
        )
    lift = pace_change - (charge or 0.0)
    score = max(0.0, min(100.0, 50 + 20 * lift / spread))

    return SongEffect(
        score=round(score, 1),
        pace_delta=round(lift, 1),
        hr_delta=None if hr_delta is None else round(hr_delta, 1),
        seconds=len(song_paces),
        position=position,
        lap_kind=kind,
        effort_charge=None if charge is None else round(charge, 1),
    )
