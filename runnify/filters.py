"""Jinja filters for showing running and listening numbers consistently.

Every page formats pace, time, distance and song effects the same way:
pace as ``4:52`` (per km), durations as ``48:12`` or ``1:02:45``, distances
as ``10.02`` (km), and effects as ``+9 s/km``. Missing values show as ``-``.
"""

from datetime import datetime

MISSING = "-"


def pace(seconds_per_km):
    """``292.4`` -> ``"4:52"`` (minutes:seconds per km)."""
    if not seconds_per_km or seconds_per_km <= 0:
        return MISSING
    total = round(seconds_per_km)
    return f"{total // 60}:{total % 60:02d}"


def run_pace(distance_m, duration_s):
    """Average pace for a whole run, from metres and seconds."""
    if not distance_m or not duration_s:
        return MISSING
    return pace(duration_s / (distance_m / 1000))


def duration(seconds):
    """``2892`` -> ``"48:12"``; ``3765`` -> ``"1:02:45"``."""
    if seconds is None:
        return MISSING
    seconds = round(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def km(metres, places=2):
    """``10021.4`` -> ``"10.02"``."""
    if metres is None:
        return MISSING
    return f"{metres / 1000:.{places}f}"


def lift(seconds_per_km):
    """``9.3`` -> ``"+9 s/km"``; ``-4.6`` -> ``"-5 s/km"`` (whole seconds, signed)."""
    if seconds_per_km is None:
        return MISSING
    value = round(seconds_per_km)
    sign = "+" if value > 0 else "-" if value < 0 else "±"
    return f"{sign}{abs(value)} s/km"


def lift_kind(seconds_per_km, threshold=1.0):
    """``"up"``, ``"down"`` or ``"flat"`` for styling an effect."""
    if seconds_per_km is None or abs(seconds_per_km) < threshold:
        return "flat"
    return "up" if seconds_per_km > 0 else "down"


def day(value):
    """``datetime(2026, 10, 5)`` -> ``"Mon 5 Oct 2026"``."""
    return f"{value:%a} {value.day} {value:%b %Y}" if value else MISSING


def short_day(value):
    """``datetime(2026, 10, 5)`` -> ``"5 Oct"``."""
    return f"{value.day} {value:%b}" if value else MISSING


def clock(value):
    """``datetime(..., 7, 5)`` -> ``"07:05"``."""
    return f"{value:%H:%M}" if value else MISSING


def ago(value, now=None):
    """Rough relative time: ``"just now"``, ``"5 min ago"``, ``"3 h ago"``, ``"2 days ago"``."""
    if value is None:
        return "never"
    from runnify.models import utcnow

    seconds = ((now or utcnow()) - value).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h ago"
    days = int(seconds // 86400)
    return f"{days} day{'s' if days != 1 else ''} ago" if days < 30 else day(value)


def plural(count, singular, plural_form=None):
    """``plural(1, "run")`` -> ``"1 run"``; ``plural(3, "run")`` -> ``"3 runs"``."""
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def initials(name):
    """``"Colm Ali"`` -> ``"CA"``."""
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


FILTERS = {
    "pace": pace,
    "run_pace": run_pace,
    "duration": duration,
    "km": km,
    "lift": lift,
    "lift_kind": lift_kind,
    "day": day,
    "short_day": short_day,
    "clock": clock,
    "ago": ago,
    "plural": plural,
    "initials": initials,
}


def init_filters(app):
    """Register every filter on ``app``'s Jinja environment."""
    app.jinja_env.filters.update(FILTERS)
    app.jinja_env.globals["now"] = datetime.now
