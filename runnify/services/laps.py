"""A run's laps: stretches of one kind of running, from the watch or from the run itself.

Songs are only fairly compared with running of the same kind: a song during a
hard rep against the other reps, a song during a jog against the other jogs.
So every run is cut into laps, each one of :data:`KINDS`.

**The watch's laps** are used when they describe the session: a structured
workout (laps marked warm-up, rest, recovery or cool-down, or tied to workout
steps), or laps the runner ended with the lap button whose paces clearly fall
into fast and slow. Laps the watch ends by itself every kilometre or mile say
nothing about the session and are ignored.

**Otherwise the run is read from its pace and heart rate.** Every second is
running, walking or stopped, judged on a 31-second rolling median of speed
(and on cadence, when the watch counted steps). Running is then split into
fast and slow stretches around the speed that separates them best. That only
counts as a structured session when the stretches are clearly apart: at least
15% in speed, with two or more fast stretches (or one long tempo block), and,
when heart rate exists, more heart rate in the fast stretches than the slow
ones, a little later, as heart rate lags. Running uphill is slow but hard, so
the heart-rate check keeps a hilly steady run steady. Walks of 30 seconds or
more are found in every run, structured or not.

All of it works in seconds of the run, which :func:`fit.at_one_hertz` makes
the same as samples.

**The kind of run** (:data:`RUN_TYPES`) follows from the laps: three or more
similar reps are intervals and uneven efforts a fartlek; one or two long hard
blocks make a tempo run; running between walks is a run-walk. A run with no
efforts is long from 75 minutes or 15 km, a tempo run when clearly quicker
than the runner's usual pace (the median over their other runs), else easy.
A race is only ever the runner's own call. Laps and types the runner set by
hand are never worked out again.
"""

import logging
from bisect import bisect_left, insort
from dataclasses import dataclass
from statistics import median, pstdev

from sqlalchemy.orm import selectinload

from runnify.extensions import db
from runnify.models import Run, RunLap

logger = logging.getLogger(__name__)

KINDS = {
    "warmup": "Warm-up",
    "hard": "Hard",
    "steady": "Steady",
    "jog": "Jog",
    "walk": "Walk",
    "cooldown": "Cool-down",
}
RUN_TYPES = {
    "easy": "Easy run",
    "long": "Long run",
    "tempo": "Tempo run",
    "intervals": "Intervals",
    "fartlek": "Fartlek",
    "run_walk": "Run-walk",
    "race": "Race",
}

MIN_LAP = 30  # seconds; shorter stretches join their neighbours
HALF_WINDOW = 15  # seconds either side of each second for the rolling median
WALK_SPEED = 1000 / 540  # m/s; slower than 9:00/km is walking
WALK_CADENCE = 140  # steps a minute; fewer is walking, whatever the pace
APART = 0.15  # fast running must be at least this much quicker than slow running
HR_LAG = 20  # seconds heart rate trails a change of effort
HR_APART = 3  # bpm more in the fast stretches, so hills don't pass for efforts
WARM_UP = 180  # seconds of slower running before the first effort to call it a warm-up
TEMPO_BLOCK = 480  # seconds a single effort needs to make a structured (tempo) run
FASTER_THAN_USUAL = 0.07  # running this much quicker than usual is hard, not steady
STRUCTURED_INTENSITIES = {"rest", "warmup", "cooldown", "recovery", "interval"}
REP_SPREAD = 0.35  # reps whose lengths vary less than this (relative to their mean) are intervals
LONG_SECONDS = 75 * 60
LONG_METRES = 15_000
TEMPO_SECONDS = 15 * 60  # a steady run needs this long to count as a tempo run
MIN_USUAL_RUNS = 3  # other runs needed before "usual pace" means anything


@dataclass
class Lap:
    """A stretch of one kind of running, from second ``start`` up to (not including) ``end``."""

    start: int
    end: int
    kind: str

    @property
    def seconds(self):
        return self.end - self.start


def steady(series):
    """The whole run as one steady lap (or no laps for an empty run)."""
    return [Lap(0, len(series), "steady")] if len(series) else []


def _rolling_median(values, half=HALF_WINDOW, minimum=10):
    """Each second's median over the window around it, ignoring gaps (``None`` if too few).

    The window slides one second at a time and stays sorted, so each step adds
    and removes a value instead of sorting the whole window again. The middle
    is taken exactly as :func:`statistics.median` takes it.
    """
    length = len(values)
    window, smoothed = [], []
    for value in values[: min(half, length)]:
        if value is not None:
            insort(window, value)
    for i in range(length):
        if i + half < length and values[i + half] is not None:
            insort(window, values[i + half])
        count = len(window)
        if count < minimum or not count:
            smoothed.append(None)
        elif count % 2:
            smoothed.append(window[count // 2])
        else:
            smoothed.append((window[count // 2 - 1] + window[count // 2]) / 2)
        if i - half >= 0 and values[i - half] is not None:
            del window[bisect_left(window, values[i - half])]
    return smoothed


def smoothed_speeds(series):
    """Rolling-median speed in m/s each second (``None`` where the runner was mostly stopped)."""
    return _rolling_median([None if p is None else 1000 / p for p in series.paces])


def _cadences(series):
    """Rolling-median cadence each second, or all ``None`` when the watch counted no steps."""
    if not series.cadences:
        return [None] * len(series)
    return _rolling_median(series.cadences)


def _smoothed(series):
    """``(speeds, cadences)``: the run's rolling-median speed and cadence each second."""
    return smoothed_speeds(series), _cadences(series)


def _state(speed, cadence):
    """What the runner was doing in one second: "run", "walk" or "stop"."""
    if speed is None:
        return "stop"
    if cadence is not None:
        return "walk" if cadence < WALK_CADENCE else "run"
    return "walk" if speed < WALK_SPEED else "run"


def _merge(stretches):
    """Join neighbours of the same kind, then fold stretches under ``MIN_LAP`` into a neighbour.

    ``stretches`` are ``[start, end, label]`` covering the run in order. The
    shortest goes first, into the longer of its neighbours, until none is short.
    """
    stretches = _joined(stretches)
    while len(stretches) > 1:
        shortest = min(range(len(stretches)), key=lambda i: stretches[i][1] - stretches[i][0])
        start, end, _ = stretches[shortest]
        if end - start >= MIN_LAP:
            break
        neighbours = [i for i in (shortest - 1, shortest + 1) if 0 <= i < len(stretches)]
        into = max(neighbours, key=lambda i: stretches[i][1] - stretches[i][0])
        stretches[shortest][2] = stretches[into][2]
        stretches = _joined(stretches)
    return stretches


def _joined(stretches):
    joined = []
    for start, end, label in stretches:
        if joined and joined[-1][2] == label:
            joined[-1][1] = end
        else:
            joined.append([start, end, label])
    return joined


def _runs_of(labels):
    """``[start, end, label]`` for each run of equal labels."""
    stretches = []
    for i, label in enumerate(labels):
        if stretches and stretches[-1][2] == label:
            stretches[-1][1] = i + 1
        else:
            stretches.append([i, i + 1, label])
    return stretches


def _split_point(values):
    """The value that best separates ``values`` into a slower and a faster group (Otsu)."""
    ordered = sorted(values)
    total, count = sum(ordered), len(ordered)
    best, best_score, running = None, 0.0, 0.0
    for k in range(1, count):
        running += ordered[k - 1]
        if ordered[k] == ordered[k - 1]:
            continue
        low, high = running / k, (total - running) / (count - k)
        score = k * (count - k) * (high - low) ** 2
        if score > best_score:
            best, best_score = (ordered[k - 1] + ordered[k]) / 2, score
    return best


def _hotter(series, fast, slow):
    """Whether heart rate ran higher in the ``fast`` stretches than the ``slow`` ones.

    ``True`` when there is too little heart rate to judge, so runs recorded
    without it are read from pace alone.
    """
    hr = series.heart_rates

    def lagged(stretches):
        return [
            hr[i]
            for s, e in stretches
            for i in range(s + HR_LAG, min(e + HR_LAG, len(hr)))
            if hr[i] is not None
        ]

    fast_hr, slow_hr = lagged(fast), lagged(slow)
    if len(fast_hr) < MIN_LAP or len(slow_hr) < MIN_LAP:
        return True
    return median(fast_hr) - median(slow_hr) >= HR_APART


def _fast_and_slow(speeds, running):
    """Each running stretch cut into ``[start, end, "fast" | "slow"]`` pieces.

    ``running`` are ``(start, end)`` stretches of running; the pieces of each
    stay inside it. The split sits at the speed that separates all the running
    best, with a little hysteresis so noise near it doesn't flicker. ``None``
    when the running is all much the same pace.
    """
    values = [speeds[i] for s, e in running for i in range(s, e) if speeds[i] is not None]
    if len(values) < 4 * MIN_LAP:
        return None
    cut = _split_point(values)
    if cut is None:
        return None
    slow = median(v for v in values if v < cut)
    fast = median(v for v in values if v > cut)
    if fast < slow * (1 + APART):
        return None
    band = (fast - slow) / 10
    parts = []
    for start, end in running:
        labels, current = [], None
        for i in range(start, end):
            speed = speeds[i]
            if speed is not None:
                if current != "fast" and speed > cut + band:
                    current = "fast"
                elif current != "slow" and speed < cut - band:
                    current = "slow"
                elif current is None:
                    current = "fast" if speed > cut else "slow"
            labels.append(current or "slow")
        parts += _merge([[start + s, start + e, label] for s, e, label in _runs_of(labels)])
    return parts


def _structured(series, parts):
    """Whether fast and slow stretches make a session rather than a run's ups and downs."""
    fast = [(s, e) for s, e, label in parts if label == "fast"]
    slow = [(s, e) for s, e, label in parts if label == "slow"]
    if not fast or not slow:
        return False
    if len(fast) == 1 and fast[0][1] - fast[0][0] < TEMPO_BLOCK:
        return False  # one short surge in an otherwise steady run
    return _hotter(series, fast, slow)


def _named(laps):
    """Join neighbouring laps of the same kind, and call the slow running either side of the
    efforts a warm-up and a cool-down when there is enough of it."""
    joined = []
    for lap in laps:
        if joined and joined[-1].kind == lap.kind:
            joined[-1].end = lap.end
        else:
            joined.append(Lap(lap.start, lap.end, lap.kind))
    hard = [i for i, lap in enumerate(joined) if lap.kind == "hard"]
    if not hard:
        return joined
    first, last = hard[0], hard[-1]
    before, after = joined[:first], joined[last + 1 :]
    middle = joined[first : last + 1]
    if before and before[-1].end - before[0].start >= WARM_UP:
        before = [Lap(before[0].start, before[-1].end, "warmup")]
    if after and after[-1].end - after[0].start >= WARM_UP:
        after = [Lap(after[0].start, after[-1].end, "cooldown")]
    return before + middle + after


def _walk_or(kind, speeds, cadences, start, end):
    """``"walk"`` when the stretch was walked or mostly stood still, else ``kind``."""
    states = [_state(speeds[i], cadences[i]) for i in range(start, end)]
    return "walk" if states.count("run") < len(states) / 2 else kind


def detect(series, usual_pace=None, smoothed=None):
    """Laps read from the run's own pace, heart rate and cadence (see the module docstring).

    Args:
        series: The run's :class:`~runnify.services.fit.Series`, one sample a second.
        usual_pace: The runner's usual pace in s/km, if known. Running between
            walks counts as hard only when it is clearly quicker than this.
        smoothed: The run's ``(speeds, cadences)`` from :func:`_smoothed`, when
            already worked out.

    Returns:
        :class:`Lap` objects covering the whole run in order.
    """
    length = len(series)
    if length < 2 * MIN_LAP:
        return steady(series)
    speeds, cadences = smoothed or _smoothed(series)
    stretches = _merge(_runs_of([_state(s, c) for s, c in zip(speeds, cadences, strict=True)]))
    running = [(s, e) for s, e, state in stretches if state == "run"]
    parts = _fast_and_slow(speeds, running)
    structured = parts is not None and _structured(series, parts)

    laps = []
    if structured:
        kinds = {"fast": "hard", "slow": "jog"}
        for start, end, state in stretches:
            if state == "run":
                laps += [Lap(s, e, kinds[label]) for s, e, label in parts if start <= s < end]
            else:  # walking, or standing still between efforts: a rest
                laps.append(Lap(start, end, "walk"))
        return _named(laps)

    walks = [(s, e) for s, e, state in stretches if state == "walk"]
    running_kind = "steady"
    if usual_pace and len(walks) >= 2:  # running between walks: easy running, or efforts?
        values = [speeds[i] for s, e in running for i in range(s, e) if speeds[i] is not None]
        if values and 1000 / median(values) < usual_pace * (1 - FASTER_THAN_USUAL):
            running_kind = "hard"
    for start, end, state in stretches:
        kind = "walk" if state == "walk" else running_kind
        if state == "stop" and laps:  # a stop in a steady run is just a stop
            kind = laps[-1].kind
        laps.append(Lap(start, end, kind))
    if laps and stretches[0][2] == "stop" and len(laps) > 1:
        laps[0].kind = laps[1].kind
    return _named(laps)


def _tidy(watch_laps, length):
    """The watch's laps as contiguous ``[start, end]`` stretches covering the whole run."""
    tidy = []
    for lap in sorted(watch_laps, key=lambda lap: lap.start):
        start = min(max(lap.start, tidy[-1][1] if tidy else 0), length)
        end = min(lap.end, length)
        if end - start >= 1:
            if tidy:
                tidy[-1][1] = start  # close any gap before this lap
            tidy.append([start, end, lap])
    if not tidy:
        return []
    tidy[0][0], tidy[-1][1] = 0, length
    return tidy


def from_watch(series, usual_pace=None, smoothed=None):
    """Laps from the watch, when they describe the session; ``None`` when they don't.

    ``smoothed`` is the run's ``(speeds, cadences)`` from :func:`_smoothed`, when
    already worked out.
    """
    tidy = _tidy(series.laps, len(series))
    if len(tidy) < 2:
        return None
    speeds, cadences = smoothed or _smoothed(series)
    workout = any(
        lap.intensity in STRUCTURED_INTENSITIES or lap.step is not None for _, _, lap in tidy
    )
    if workout:
        return _workout_laps(tidy, speeds, cadences, usual_pace)
    if all(lap.trigger in ("manual", "session_end", None) for _, _, lap in tidy):
        return _button_laps(series, tidy, speeds, cadences)
    return None  # laps the watch ended every kilometre or mile


def _speed_over(speeds, stretches):
    """The median speed over ``(start, end)`` stretches (``None`` if they were all stopped)."""
    values = [
        speeds[i] for start, end in stretches for i in range(start, end) if speeds[i] is not None
    ]
    return median(values) if values else None


def _workout_laps(tidy, speeds, cadences, usual_pace):
    """Laps of a structured workout, named from their intensity and how they were run.

    Work steps between jogged recoveries are efforts. Without jogs (a run-walk,
    or Garmin's suggested easy runs: warm-up, run, cool-down) a work step is hard
    only when clearly quicker than the warm-up and cool-down, or than usual.
    """
    laps = []
    for start, end, lap in tidy:
        if lap.intensity in ("warmup", "cooldown"):
            kind = lap.intensity
        elif lap.intensity in ("rest", "recovery"):
            kind = _walk_or("jog", speeds, cadences, start, end)
        elif lap.intensity == "interval":
            kind = "hard"
        else:
            kind = "work"
        laps.append(Lap(start, end, kind))
    work = [lap for lap in laps if lap.kind == "work"]
    hard = any(lap.kind == "jog" for lap in laps)
    if not hard and work:
        work_speed = _speed_over(speeds, [(lap.start, lap.end) for lap in work])
        easy_speed = _speed_over(
            speeds,
            [(lap.start, lap.end) for lap in laps if lap.kind in ("warmup", "cooldown")],
        )
        hard = work_speed is not None and (
            (easy_speed is not None and work_speed >= easy_speed * (1 + APART))
            or (usual_pace and 1000 / work_speed < usual_pace * (1 - FASTER_THAN_USUAL))
        )
    for lap in work:
        lap.kind = "hard" if hard else "steady"
    return laps


def _button_laps(series, tidy, speeds, cadences):
    """Laps ended with the lap button, when their paces clearly fall into fast and slow.

    Where pace and heart rate disagree (hill reps are slow but hard), heart rate
    decides which laps were the efforts.
    """
    lap_speeds = [_speed_over(speeds, [(start, end)]) for start, end, _ in tidy]
    known = [v for v in lap_speeds if v is not None]
    cut = _split_point(known) if len(known) >= 3 else None
    if cut is None:
        return None
    pairs = list(zip(tidy, lap_speeds, strict=True))
    fast = [(s, e) for (s, e, _), v in pairs if v is not None and v > cut]
    slow = [(s, e) for (s, e, _), v in pairs if v is None or v <= cut]
    fast_speed = median(v for v in known if v > cut)
    slow_speed = median(v for v in known if v <= cut)
    if len(fast) < 2 or fast_speed < slow_speed * (1 + APART):
        return None
    efforts = set(fast) if _hotter(series, fast, slow) else set(slow)
    laps = []
    for start, end, _ in tidy:
        kind = "hard" if (start, end) in efforts else "jog"
        laps.append(Lap(start, end, _walk_or(kind, speeds, cadences, start, end)))
    return _named(laps)


def find_laps(series, usual_pace=None):
    """The run's laps and where they came from: ``(laps, "watch" | "detected")``."""
    smoothed = _smoothed(series)  # once, for both readings of the run
    watch = from_watch(series, usual_pace, smoothed)
    if watch:
        return watch, "watch"
    return detect(series, usual_pace, smoothed), "detected"


def run_type(laps, seconds, metres, usual_pace=None):
    """The kind of run (a :data:`RUN_TYPES` key) from its laps and totals; never "race".

    Args:
        laps: The run's :class:`Lap` objects.
        seconds, metres: The run's duration and distance.
        usual_pace: The runner's usual pace in s/km, or ``None`` if not known yet.
    """
    hard = [lap.seconds for lap in laps if lap.kind == "hard"]
    walked = sum(lap.seconds for lap in laps if lap.kind == "walk")
    walks = sum(lap.kind == "walk" for lap in laps)
    if len(hard) >= 3:
        return "intervals" if pstdev(hard) <= REP_SPREAD * (sum(hard) / len(hard)) else "fartlek"
    if hard:
        return "tempo" if all(length >= TEMPO_BLOCK for length in hard) else "fartlek"
    if walks >= 2 and walked >= 0.1 * seconds:
        return "run_walk"
    if seconds >= LONG_SECONDS or metres >= LONG_METRES:
        return "long"
    quick = (
        usual_pace
        and metres > 0
        and seconds / (metres / 1000) < usual_pace * (1 - FASTER_THAN_USUAL)
    )
    return "tempo" if quick and seconds >= TEMPO_SECONDS else "easy"


def lap_stats(series, start, end):
    """``(distance, moving_seconds, average_heart_rate)`` from second ``start`` to ``end``.

    Distance comes from the watch's own distance when the stream has it, else
    from the pace each moving second.
    """
    distances, paces = series.distances, series.paces[start:end]
    last = min(end, len(series) - 1)
    if distances and distances[start] is not None and distances[last] is not None:
        distance = distances[last] - distances[start]
    else:
        distance = sum(1000 / pace for pace in paces if pace is not None)
    heart = [h for h in series.heart_rates[start:end] if h is not None]
    return (
        round(distance, 1),
        sum(pace is not None for pace in paces),
        round(sum(heart) / len(heart)) if heart else None,
    )


def kinds_by_second(laps, length):
    """The kind of lap at each second of a ``length``-second run (``None`` where none covers it)."""
    kinds = [None] * length
    for lap in laps:
        for second in range(max(lap.start, 0), min(lap.end, length)):
            kinds[second] = lap.kind
    return kinds


def laps_of(run):
    """``run``'s stored laps as :class:`Lap` objects, in order."""
    return [Lap(lap.start_second, lap.end_second, lap.kind) for lap in run.laps]


def store_laps(run, series, laps, source):
    """Replace ``run``'s laps with ``laps``, which came from ``source``, described from ``series``."""
    rows = []
    for position, lap in enumerate(laps):
        distance, moving, heart = lap_stats(series, lap.start, lap.end)
        rows.append(
            RunLap(
                position=position,
                start_second=lap.start,
                end_second=lap.end,
                kind=lap.kind,
                distance=distance,
                moving_seconds=moving,
                avg_hr=heart,
            )
        )
    run.laps = rows
    run.laps_source = source if rows else None


def _paces(user_id):
    """``{run id: pace in s/km}`` for the runner's runs long enough to judge a pace by."""
    rows = db.session.query(Run.id, Run.duration, Run.distance).filter(
        Run.user_id == user_id, Run.distance >= 1000, Run.duration > 0
    )
    return {run_id: duration / (distance / 1000) for run_id, duration, distance in rows}


class UsualPaces:
    """The runner's usual pace with any one run left out, for many runs at once.

    :func:`usual_pace` sorts every pace again for each run; this sorts them
    once, so working out the usual pace of each of a thousand runs stays quick.

    Args:
        paces: ``{key: pace in s/km}``, as :func:`_paces` gives them (keys are
            usually run ids).
    """

    def __init__(self, paces):
        self.paces = dict(paces)
        self._ordered = sorted(self.paces.values())

    @classmethod
    def for_runner(cls, user_id):
        """The paces of every run of the runner's long enough to judge a pace by."""
        return cls(_paces(user_id))

    def excluding(self, key):
        """The median of the paces other than ``key``'s (``None`` with too few of them).

        The middle is taken exactly as :func:`statistics.median` takes it.
        """
        ordered, own = self._ordered, self.paces.get(key)
        gap = len(ordered) if own is None else bisect_left(ordered, own)  # where own pace sat
        count = len(ordered) - (own is not None)
        if count < MIN_USUAL_RUNS:
            return None

        def nth(i):  # the i-th of the other paces, in order
            return ordered[i] if i < gap else ordered[i + 1]

        middle = count // 2
        return nth(middle) if count % 2 else (nth(middle - 1) + nth(middle)) / 2


def usual_pace(user_id, exclude=None, paces=None):
    """The runner's usual pace in s/km: the median over their runs other than ``exclude``.

    ``None`` until there are :data:`MIN_USUAL_RUNS` of them. ``paces`` (from
    :func:`_paces`) saves a query; for many runs, use :class:`UsualPaces`.
    """
    return UsualPaces(_paces(user_id) if paces is None else paces).excluding(exclude)


LOOK_UP = object()  # "work the usual pace out", where None means "not known yet"


def refresh_laps(run, series, usual=LOOK_UP):
    """Work out ``run``'s laps and type again, keeping whatever the runner set by hand.

    A failure is logged and leaves the laps as they were, so it can never stop
    a sync or an import.

    Args:
        run: The :class:`Run`.
        series: Its samples.
        usual: The runner's usual pace without this run (:func:`usual_pace`), when
            already worked out; refreshing many runs, :class:`UsualPaces` saves a
            query for each.

    Returns:
        The run's laps as :class:`Lap` objects.
    """
    if usual is LOOK_UP:
        usual = usual_pace(run.user_id, exclude=run.id)
    if run.laps_source != "manual" and len(series):
        try:
            laps, source = find_laps(series, usual)
        except Exception:
            logger.exception("Couldn't work out the laps of run %s", run.id)
        else:
            store_laps(run, series, laps, source)
    laps = laps_of(run)
    if not run.run_type_manual:
        run.run_type = run_type(laps, run.duration or len(series), run.distance or 0, usual)
    return laps


def retype_runs(user_id):
    """Work out again the type of each of the runner's runs that they haven't set by hand.

    Done after every sync and import, so runs stored before there was a usual
    pace to judge them by get one.
    """
    paces = UsualPaces.for_runner(user_id)
    runs = Run.query.options(selectinload(Run.laps)).filter_by(
        user_id=user_id, run_type_manual=False
    )
    for run in runs:
        run.run_type = run_type(
            laps_of(run), run.duration or 0, run.distance or 0, paces.excluding(run.id)
        )


# ---- changes the runner makes by hand ---------------------------------------

MIN_SPLIT = 10  # seconds a split must leave either side, so no lap is all edge


class LapError(ValueError):
    """A change to a run's laps that can't be made; the message is safe to show."""


STALE = "Those laps have changed since the page loaded. Have another look and try again."


def parse_time(text):
    """Seconds from a time into the run: ``"12:30"``, ``"1:02:30"`` or whole minutes ``"12"``.

    ``None`` when ``text`` isn't one.
    """
    parts = (text or "").strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    if len(parts) == 1:
        return int(parts[0]) * 60
    *bigger, seconds = (int(part) for part in parts)
    if seconds >= 60 or (len(bigger) == 2 and bigger[1] >= 60):
        return None
    minutes = bigger[-1] + (bigger[0] * 60 if len(bigger) == 2 else 0)
    return minutes * 60 + seconds


def set_run_type(run, run_type):
    """Set the kind of run by hand, or ``"auto"`` to have it worked out again."""
    if run_type == "auto":
        run.run_type_manual = False
    elif run_type in RUN_TYPES:
        run.run_type, run.run_type_manual = run_type, True
    else:
        raise LapError("Pick a kind of run from the list.")


def set_kinds(run, series, kinds):
    """Give each of the run's laps the kind in ``kinds``, in order."""
    laps = laps_of(run)
    if len(kinds) != len(laps):
        raise LapError(STALE)
    if any(kind not in KINDS for kind in kinds):
        raise LapError("Pick a kind for every lap.")
    store_laps(
        run,
        series,
        [Lap(lap.start, lap.end, kind) for lap, kind in zip(laps, kinds, strict=True)],
        "manual",
    )


def merge_laps(run, series, position):
    """Join lap ``position`` (counting from 0) with the next one, keeping its kind."""
    laps = laps_of(run)
    if not 0 <= position < len(laps) - 1:
        raise LapError(STALE)
    first, second = laps[position], laps[position + 1]
    laps[position : position + 2] = [Lap(first.start, second.end, first.kind)]
    store_laps(run, series, laps, "manual")


def split_lap(run, series, second):
    """Split the lap that ``second`` falls in into two of the same kind; returns its position."""
    laps = laps_of(run)
    for position, lap in enumerate(laps):
        if lap.start + MIN_SPLIT <= second <= lap.end - MIN_SPLIT:
            laps[position : position + 1] = [
                Lap(lap.start, second, lap.kind),
                Lap(second, lap.end, lap.kind),
            ]
            store_laps(run, series, laps, "manual")
            return position
    raise LapError("Give a time inside a lap, at least 10 seconds from either end, like 12:30.")


def reset_laps(run):
    """Forget the laps set by hand, so the next refresh works them out again."""
    run.laps_source = None
    run.workout = None
