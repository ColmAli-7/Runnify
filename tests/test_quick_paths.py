"""The quick versions of laps and scoring give exactly what the straightforward ones give.

Each ``_straightforward_*`` function below is the code as it was before it was
made quick, kept here as the reference: the rolling median sorting every
window, the usual pace sorting every run's others, and a song's effect found
by scanning the whole run. Random runs exercise every path.
"""

import random
from collections import Counter
from datetime import datetime, timedelta
from statistics import median

import pytest

from runnify.services import laps as L
from runnify.services import scoring as S
from runnify.services.fit import Series

START = datetime(2026, 10, 1, 7, 0)


def _straightforward_rolling_median(values, half, minimum):
    smoothed = []
    for i in range(len(values)):
        window = [v for v in values[max(i - half, 0) : i + half + 1] if v is not None]
        smoothed.append(median(window) if len(window) >= minimum else None)
    return smoothed


def _straightforward_usual(paces, exclude):
    others = [pace for key, pace in paces.items() if key != exclude]
    return median(others) if len(others) >= L.MIN_USUAL_RUNS else None


def _straightforward_heart(series, indexes):
    heart_rates, cadences = series.heart_rates, series.cadences
    found = []
    for i in indexes:
        j = i + S.HR_LAG
        if j >= len(heart_rates) or heart_rates[j] is None:
            continue
        if (
            cadences
            and cadences[j] is not None
            and abs(heart_rates[j] - cadences[j]) <= S.CADENCE_LOCK
        ):
            continue
        found.append(heart_rates[j])
    return found


def _straightforward_effect(series, start, end, kinds=None):
    timestamps, paces = series.timestamps, series.paces
    if not timestamps:
        return S.SongEffect(None, None, None, 0, 0.0)
    run_start, run_end = timestamps[0], timestamps[-1]
    duration = (run_end - run_start).total_seconds() or 1.0
    position = round(min(max((start - run_start).total_seconds() / duration, 0.0), 1.0), 3)
    inside = [i for i, t in enumerate(timestamps) if start <= t <= end]
    near = [
        i
        for i, t in enumerate(timestamps)
        if (start - S.CONTEXT <= t < start) or (end < t <= end + S.CONTEXT)
    ]
    kind, alike = None, None
    if kinds is not None:
        usable = S.usable_kinds(kinds)
        found = Counter(usable[i] for i in inside if usable[i] is not None and paces[i] is not None)
        if not found:
            return S.SongEffect(None, None, None, 0, position)
        kind = found.most_common(1)[0][0]
        alike = [i for i, k in enumerate(usable) if k == kind]
        inside = [i for i in inside if usable[i] == kind]
        near = [i for i in near if usable[i] == kind]
    song_paces = [paces[i] for i in inside if paces[i] is not None]
    if len(song_paces) < S.MIN_SONG_SAMPLES:
        return S.SongEffect(None, None, None, len(song_paces), position, kind)
    context_paces = [paces[i] for i in near if paces[i] is not None]
    if len(context_paces) < S.MIN_CONTEXT_SAMPLES:
        span = {i for i, t in enumerate(timestamps) if start <= t <= end}
        rest = alike if alike is not None else range(len(timestamps))
        near = [i for i in rest if i not in span]
        context_paces = [paces[i] for i in near if paces[i] is not None]
        if len(context_paces) < S.MIN_CONTEXT_SAMPLES:
            return S.SongEffect(None, None, None, len(song_paces), position, kind)
    compared = [paces[i] for i in (alike if alike is not None else range(len(paces)))]
    spread = max(S._robust_spread([p for p in compared if p is not None]), S.MIN_SPREAD)
    pace_change = median(context_paces) - median(song_paces)
    song_hr, context_hr = (
        _straightforward_heart(series, inside),
        _straightforward_heart(series, near),
    )
    hr_delta = median(song_hr) - median(context_hr) if song_hr and context_hr else None
    charge = None
    if kind in S.CHARGED_KINDS:
        charge = S.effort_charge(
            pace_change, hr_delta, median(context_paces), median(context_hr) if context_hr else None
        )
    lift = pace_change - (charge or 0.0)
    score = max(0.0, min(100.0, 50 + 20 * lift / spread))
    return S.SongEffect(
        score=round(score, 1),
        pace_delta=round(lift, 1),
        hr_delta=None if hr_delta is None else round(hr_delta, 1),
        seconds=len(song_paces),
        position=position,
        lap_kind=kind,
        effort_charge=None if charge is None else round(charge, 1),
    )


def _random_run(rng, seconds):
    """A run of ``seconds`` with efforts, walks, stops, missing heart rate and cadence lock."""
    shape = rng.choice(("steady", "intervals", "run-walk", "hills"))
    paces, hearts, cadences = [], [], []
    for s in range(seconds):
        if shape == "intervals" and 300 <= s < seconds - 200 and (s - 300) % 240 < 120:
            pace, heart = 255.0, 170
        elif shape == "run-walk" and (s // 150) % 3 == 2:
            pace, heart = 690.0, 120
        elif shape == "hills":
            pace, heart = 320.0 + 35 * ((s // 90) % 2), 150 + 8 * ((s // 90) % 2)
        else:
            pace, heart = 310.0, 148
        paces.append(None if rng.random() < 0.03 else round(pace + rng.uniform(-9, 9), 1))
        hearts.append(None if rng.random() < 0.05 else heart + rng.randint(-3, 3))
        cadence = 118 if pace > 540 else 170 + rng.randint(-3, 3)
        if rng.random() < 0.01:
            cadence = hearts[-1]  # a wrist sensor locked onto the steps
        cadences.append(cadence)
    return Series(
        timestamps=[START + timedelta(seconds=s) for s in range(seconds)],
        heart_rates=hearts,
        paces=paces,
        cadences=cadences if rng.random() < 0.6 else [],
    )


@pytest.mark.parametrize("seed", range(6))
def test_the_rolling_median_matches_a_median_of_each_window(seed):
    rng = random.Random(seed)  # noqa: S311  (test data)
    for _ in range(40):
        length = rng.choice([0, 1, 7, 60, 400])
        gaps = rng.choice([0.0, 0.2, 0.7, 1.0])
        values = [None if rng.random() < gaps else rng.uniform(1, 5) for _ in range(length)]
        if rng.random() < 0.3:
            values = [None if v is None else round(v) for v in values]  # ties, and ints
        half, minimum = rng.choice([(15, 10), (3, 2), (0, 1), (40, 31)])
        assert L._rolling_median(values, half, minimum) == _straightforward_rolling_median(
            values, half, minimum
        )


@pytest.mark.parametrize("count", [0, 2, 3, 4, 5, 9, 40])
def test_usual_paces_match_the_median_of_the_other_runs(count):
    rng = random.Random(count)  # noqa: S311  (test data)
    paces = {n: rng.choice([300.0, 312.5, rng.uniform(250, 400)]) for n in range(count)}
    usual = L.UsualPaces(paces)
    for left_out in [*paces, None, "not a run"]:
        assert usual.excluding(left_out) == _straightforward_usual(paces, left_out)


@pytest.mark.parametrize("seed", range(8))
def test_every_song_measures_as_the_straightforward_way_measures_it(seed):
    rng = random.Random(seed)  # noqa: S311  (test data)
    series = _random_run(rng, rng.choice([600, 1500, 2400]))
    laps, _ = L.find_laps(series, rng.choice([None, 300.0]))
    songs = []
    for _ in range(25):
        start = rng.randint(-60, len(series) + 30)
        end = start + rng.choice([0, 10, 25, 120, 200, 300])
        songs.append((START + timedelta(seconds=start), START + timedelta(seconds=end)))
    for kinds in (L.kinds_by_second(laps, len(series)), None):
        scorer = S.RunScorer(series, kinds)
        for start, end in songs:
            expected = _straightforward_effect(series, start, end, kinds)
            assert scorer.effect(start, end) == expected
            assert S.song_effect(series, start, end, kinds) == expected


def test_samples_out_of_order_measure_as_the_straightforward_way_does():
    rng = random.Random(99)  # noqa: S311  (test data)
    series = _random_run(rng, 900)
    order = list(range(len(series)))
    rng.shuffle(order)
    shuffled = Series(
        timestamps=[series.timestamps[i] for i in order],
        heart_rates=[series.heart_rates[i] for i in order],
        paces=[series.paces[i] for i in order],
    )
    for start, end in [(100, 300), (0, 200), (700, 900), (400, 380)]:
        start, end = START + timedelta(seconds=start), START + timedelta(seconds=end)
        assert S.song_effect(shuffled, start, end) == _straightforward_effect(shuffled, start, end)
