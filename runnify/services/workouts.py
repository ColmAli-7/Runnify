"""Workouts the runner types, read into steps and lined up with the run.

"15 min warm-up, 6 x 3 min hard with 2 min jog, 10 min cool-down" reads as a
warm-up, six reps with a jog after each, and a cool-down. Steps are separated
by commas, semicolons, "then" or new lines; a repeat is "6 x ..." or "... x 6",
with its parts in brackets or joined by "with" or "/". Amounts are minutes
("3 min", "3'"), seconds ("90 s", "1:30"), kilometres ("1 km", "5k"), metres
("400 m") or miles, and each step names its kind: warm-up, hard, steady (or
easy), jog, walk or cool-down, in plain words or the usual shorthand (wu, cd,
rep, rec). Inside a repeat, unnamed parts are the efforts and then the
recoveries, and "easy" after an effort is a jog. Pace targets ("@ 5k pace")
are read past.

Only what was read is kept: the workout is stored as Runnify writes it back
from its steps (:func:`describe`), never as typed, so a note such as an injury
never ends up stored.

Lining up places each step after the one before, by time or by distance, and
snaps each change to the biggest real change in pace near where the plan puts
it. Placing each step from the last real change, not from the start, keeps a
slow first rep from pushing every later one out of line.
"""

import re
from dataclasses import dataclass
from statistics import median

from runnify.services.laps import MIN_LAP, MIN_SPLIT, Lap, LapError, smoothed_speeds, store_laps

MAX_REPEATS = 50
MAX_WRITTEN = 300  # the most of a workout a run keeps (Run.workout)
MAX_STEPS = 200
SNAP_WINDOW = 45  # seconds either side of a planned change to look for the real one
SNAP_LOOK = 15  # seconds of running either side of a candidate change compared
SNAP_SHARE = 0.25  # never look further than this share of the step's own length
SNAP_MIN_CHANGE = 0.05  # a change of pace smaller than this share of the speed is noise

WORDS = {
    "warmup": "warmup",
    "wu": "warmup",
    "cooldown": "cooldown",
    "cd": "cooldown",
    "hard": "hard",
    "fast": "hard",
    "on": "hard",
    "effort": "hard",
    "efforts": "hard",
    "rep": "hard",
    "reps": "hard",
    "interval": "hard",
    "intervals": "hard",
    "tempo": "hard",
    "threshold": "hard",
    "strong": "hard",
    "sprint": "hard",
    "sprints": "hard",
    "quick": "hard",
    "work": "hard",
    "steady": "steady",
    "easy": "steady",
    "run": "steady",
    "running": "steady",
    "comfortable": "steady",
    "jog": "jog",
    "jogging": "jog",
    "recovery": "jog",
    "recover": "jog",
    "rec": "jog",
    "float": "jog",
    "walk": "walk",
    "walking": "walk",
    "rest": "walk",
}
NAMES = {
    "warmup": "warm-up",
    "hard": "hard",
    "steady": "steady",
    "jog": "jog",
    "walk": "walk",
    "cooldown": "cool-down",
}
UNITS = {
    "min": ("s", 60),
    "mins": ("s", 60),
    "minute": ("s", 60),
    "minutes": ("s", 60),
    "'": ("s", 60),
    "s": ("s", 1),
    "sec": ("s", 1),
    "secs": ("s", 1),
    "second": ("s", 1),
    "seconds": ("s", 1),
    '"': ("s", 1),
    "km": ("m", 1000),
    "k": ("m", 1000),
    "kilometre": ("m", 1000),
    "kilometres": ("m", 1000),
    "kilometer": ("m", 1000),
    "kilometers": ("m", 1000),
    "m": ("m", 1),
    "metre": ("m", 1),
    "metres": ("m", 1),
    "meter": ("m", 1),
    "meters": ("m", 1),
    "mi": ("m", 1609.344),
    "mile": ("m", 1609.344),
    "miles": ("m", 1609.344),
}
_UNIT = "|".join(sorted((re.escape(unit) for unit in UNITS), key=len, reverse=True))
AMOUNT = re.compile(
    rf"(?P<clock>\d+:\d{{2}})|(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT})(?![a-z])"
)
WORD = re.compile(r"[a-z]+")
LEADING_REPEAT = re.compile(r"^(?P<count>\d+)\s*x\s*(?P<inner>.+)$")
TRAILING_REPEAT = re.compile(r"^(?P<inner>.+?)\s*x\s*(?P<count>\d+)$")
EXAMPLE = "15 min warm-up, 6 x 3 min hard with 2 min jog, 10 min cool-down"


class WorkoutError(LapError):
    """Text that can't be read as a workout; the message says what to change."""


@dataclass
class Step:
    """One step of a workout: so much of one kind of running."""

    kind: str  # services.laps.KINDS key
    amount: float  # seconds or metres
    unit: str  # "s" (time) or "m" (distance)


@dataclass
class Block:
    """Steps done ``count`` times over (once for a plain step)."""

    count: int
    steps: list[Step]


def _normalised(text):
    # a multiplication sign, and curly minute and second marks, as phones type them
    text = text.lower().replace("×", "x").replace("’", "'").replace("”", '"')  # noqa: RUF001
    text = re.sub(r"\bwarm[\s-]+up\b", "warmup", text)
    text = re.sub(r"\bcool[\s-]+down\b", "cooldown", text)
    text = re.sub(r"\btimes\b", "x", text)
    text = re.sub(r"@[^,;/()\n]*", " ", text)  # pace targets: "@ 5k pace"
    text = re.sub(r"\bat\s+[^,;/()\n]*?pace\b", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _chunks(text):
    """The workout's top-level steps, split at commas, semicolons, "then" and new lines,
    but not inside brackets."""
    chunks, depth, current = [], 0, ""
    for piece in re.split(r"([(),;\n]|\bthen\b)", text):
        if piece == "(":
            depth += 1
        elif piece == ")":
            depth = max(depth - 1, 0)
        if depth == 0 and piece in (",", ";", "\n", "then"):
            chunks.append(current)
            current = ""
        else:
            current += piece
    chunks.append(current)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _kind_in(text):
    """The first kind word in ``text``, or ``None``."""
    for word in WORD.findall(text):
        if word in WORDS:
            return WORDS[word]
    return None


def _last_kind_in(text):
    kinds = [WORDS[word] for word in WORD.findall(text) if word in WORDS]
    return kinds[-1] if kinds else None


def _amounts(text):
    """``(seconds or metres, unit, kind or None)`` for each amount in ``text``, in order.

    A kind is read from the words after its amount ("3 min hard"), or before it
    when the text starts with a kind ("run 4 min walk 1 min").
    """
    found = list(AMOUNT.finditer(text))
    if not found:
        return []
    kind_first = _kind_in(text[: found[0].start()]) is not None
    amounts = []
    for i, match in enumerate(found):
        if match.group("clock"):
            minutes, seconds = match.group("clock").split(":")
            amount, unit = int(minutes) * 60 + int(seconds), "s"
        else:
            unit, scale = UNITS[match.group("unit")]
            amount = float(match.group("number")) * scale
        before = text[found[i - 1].end() if i else 0 : match.start()]
        after = text[match.end() : found[i + 1].start() if i + 1 < len(found) else len(text)]
        kind = _last_kind_in(before) if kind_first else _kind_in(after)
        amounts.append((amount, unit, kind))
    return amounts


def _block(chunk):
    """One top-level step, or a repeat, as a :class:`Block`."""
    count, inner = 1, chunk
    for pattern in (LEADING_REPEAT, TRAILING_REPEAT):
        if match := pattern.match(chunk):
            count, inner = int(match.group("count")), match.group("inner").strip("() ")
            break
    amounts = _amounts(inner)
    if not amounts:
        raise WorkoutError(
            f"Runnify couldn't find a time or a distance in “{chunk}”. "
            f"Write each step with one, like {EXAMPLE}."
        )
    if not 1 <= count <= MAX_REPEATS:
        raise WorkoutError(f"Repeat a step between 1 and {MAX_REPEATS} times.")
    steps = []
    repeated = count > 1 or len(amounts) > 1
    hard_part = any(kind == "hard" for _, _, kind in amounts)
    for position, (amount, unit, kind) in enumerate(amounts):
        if kind is None:
            if not repeated:
                raise WorkoutError(
                    f"Say what kind of running “{chunk}” is: warm-up, hard, steady, jog, "
                    "walk or cool-down."
                )
            kind = "hard" if position == 0 else "jog"  # the effort, then the recovery
        elif kind == "steady" and repeated and hard_part and position > 0:
            kind = "jog"  # "3 min hard, 2 min easy": the easy part is the recovery
        if amount <= 0:
            raise WorkoutError(f"Every step needs some time or distance: “{chunk}” has none.")
        steps.append(Step(kind, amount, unit))
    return Block(count, steps)


def parse(text):
    """The workout in ``text`` as :class:`Block` objects.

    Raises:
        WorkoutError: Part of it couldn't be read; the message says which.
    """
    chunks = _chunks(_normalised(text or ""))
    if not chunks:
        raise WorkoutError(f"Write the workout out, like {EXAMPLE}.")
    blocks = [_block(chunk) for chunk in chunks]
    if sum(block.count * len(block.steps) for block in blocks) > MAX_STEPS:
        raise WorkoutError(f"That workout has more than {MAX_STEPS} steps.")
    return blocks


def steps_of(blocks):
    """Every step in order, repeats written out."""
    return [step for block in blocks for _ in range(block.count) for step in block.steps]


def _amount_text(step):
    if step.unit == "m":
        if step.amount >= 1000:
            return f"{step.amount / 1000:g} km"
        return f"{step.amount:g} m"
    seconds = round(step.amount)
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    if seconds < 120:
        return f"{seconds} s"
    return f"{seconds // 60}:{seconds % 60:02d}"


def describe(blocks):
    """The workout written back from its steps, as Runnify stores and shows it."""
    parts = []
    for block in blocks:
        steps = ", ".join(f"{_amount_text(step)} {NAMES[step.kind]}" for step in block.steps)
        if block.count == 1:
            parts.append(steps)
        elif len(block.steps) == 1:
            parts.append(f"{block.count} x {steps}")
        else:
            parts.append(f"{block.count} x ({steps})")
    return ", ".join(parts)


def _distances(series):
    """Metres from the start at each second: the watch's own, or added up from pace."""
    if series.distances:
        distances, last = [], 0.0
        for distance in series.distances:
            last = last if distance is None else distance
            distances.append(last)
        return distances
    distances, total = [], 0.0
    for pace in series.paces:
        total += 0.0 if pace is None else 1000 / pace
        distances.append(total)
    return distances


def _change_at(speeds, second):
    """How much the pace changes at ``second``: running just after against just before."""
    before = [v for v in speeds[max(second - SNAP_LOOK, 0) : second] if v is not None]
    after = [v for v in speeds[second : second + SNAP_LOOK] if v is not None]
    if not before or not after:
        return 0.0
    return abs(median(after) - median(before))


def _snapped(speeds, planned, low, high, reach, typical):
    """The second near ``planned`` (within ``reach``, between ``low`` and ``high``) where the
    pace changes most, or ``planned`` when nothing there stands out from the noise of a run
    whose usual speed is ``typical``."""
    candidates = range(max(planned - reach, low), min(planned + reach, high) + 1)
    if not candidates:
        return planned
    best = max(candidates, key=lambda second: (_change_at(speeds, second), -abs(second - planned)))
    return best if _change_at(speeds, best) >= SNAP_MIN_CHANGE * typical else planned


def line_up(blocks, series):
    """Laps for the workout ``blocks`` along ``series``, each step placed after the last.

    Steps the run didn't get to are left out; running after the last step is
    a cool-down (or steady running, after a workout with no efforts).
    """
    length = len(series)
    steps = steps_of(blocks)
    if not length or not steps:
        return []
    speeds, distances = smoothed_speeds(series), _distances(series)
    moving = [speed for speed in speeds if speed is not None]
    typical = median(moving) if moving else 0.0
    laps, start = [], 0
    for index, step in enumerate(steps):
        if start >= length - MIN_SPLIT:
            break
        if step.unit == "s":
            planned = start + round(step.amount)
        else:
            target = distances[start] + step.amount
            planned = next((s for s in range(start, length) if distances[s] >= target), length)
        planned = min(planned, length)
        if index < len(steps) - 1 and planned < length - MIN_SPLIT:
            reach = min(SNAP_WINDOW, max(round(SNAP_SHARE * (planned - start)), MIN_SPLIT))
            end = _snapped(speeds, planned, start + MIN_SPLIT, length - MIN_SPLIT, reach, typical)
        else:
            end = planned
        if end > start:
            laps.append(Lap(start, end, step.kind))
            start = end
    if start < length:
        if length - start < MIN_LAP and laps:
            laps[-1].end = length
        else:
            after = "cooldown" if any(lap.kind == "hard" for lap in laps) else "steady"
            laps.append(Lap(start, length, after))
    return laps


def apply_workout(run, series, text):
    """Read ``text`` as a workout and make it ``run``'s laps; returns them.

    The workout is kept as Runnify writes it back, never as typed.

    Raises:
        WorkoutError: The text couldn't be read, or wouldn't fit the run.
    """
    blocks = parse(text)
    written = describe(blocks)
    if len(written) > MAX_WRITTEN:
        raise WorkoutError("That workout is too long to keep. Join some of its steps up.")
    laps = line_up(blocks, series)
    if not laps:
        raise WorkoutError("This run has no second-by-second recording to line a workout up with.")
    store_laps(run, series, laps, "manual")
    run.workout = written
    return laps
