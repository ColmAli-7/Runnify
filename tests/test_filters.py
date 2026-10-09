"""Display formatting shared by every page."""

from datetime import datetime, timedelta

import pytest

from runnify import filters


@pytest.mark.parametrize(
    ("value", "expected"), [(292.4, "4:52"), (300, "5:00"), (59.6, "1:00"), (None, "-"), (0, "-")]
)
def test_pace(value, expected):
    assert filters.pace(value) == expected


def test_run_pace():
    assert filters.run_pace(10_000, 2892) == "4:49"
    assert filters.run_pace(0, 100) == "-"


@pytest.mark.parametrize(
    ("value", "expected"), [(2892, "48:12"), (3765, "1:02:45"), (59, "0:59"), (None, "-")]
)
def test_duration(value, expected):
    assert filters.duration(value) == expected


def test_km():
    assert filters.km(10021.4) == "10.02"
    assert filters.km(5000, places=1) == "5.0"


@pytest.mark.parametrize(
    ("value", "text", "kind"),
    [
        (9.3, "+9\u00a0s/km", "up"),
        (-4.6, "\u22125\u00a0s/km", "down"),
        (0.2, "±0\u00a0s/km", "flat"),
        (None, "-", "flat"),
    ],
)
def test_lift(value, text, kind):
    assert filters.lift(value) == text
    assert filters.lift_kind(value) == kind
    assert filters.lift_number(value) == text.split(chr(0xA0))[0]


def test_dates():
    when = datetime(2026, 10, 5, 7, 5)
    assert filters.day(when) == "Mon 5 Oct 2026"
    assert filters.short_day(when) == "5 Oct"
    assert filters.clock(when) == "07:05"


def test_ago():
    now = datetime(2026, 10, 9, 12, 0)
    assert filters.ago(now - timedelta(seconds=20), now=now) == "just now"
    assert filters.ago(now - timedelta(minutes=5), now=now) == "5 min ago"
    assert filters.ago(now - timedelta(hours=3), now=now) == "3 h ago"
    assert filters.ago(now - timedelta(days=2), now=now) == "2 days ago"
    assert filters.ago(None) == "never"


def test_plural_and_initials():
    assert filters.plural(1, "run") == "1 run"
    assert filters.plural(3, "run") == "3 runs"
    assert filters.initials("Colm Ali") == "CA"
    assert filters.initials("Cher") == "C"
    assert filters.initials("") == "?"
