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


@pytest.mark.parametrize(
    ("hour", "name"),
    [
        (6, "Morning run"),
        (12, "Lunch run"),
        (15, "Afternoon run"),
        (19, "Evening run"),
        (23, "Night run"),
        (2, "Night run"),
    ],
)
def test_run_name(hour, name):
    assert filters.run_name(datetime(2026, 10, 5, hour, 30)) == name


def test_first_name():
    assert filters.first_name("Colm Ali") == "Colm"
    assert filters.first_name("  ") == ""


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
            "Chrome on Windows",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Firefox on Linux",
        ),
        ("", "Unknown device"),
        (None, "Unknown device"),
    ],
)
def test_device(agent, expected):
    assert filters.device(agent) == expected


def test_network():
    assert filters.network("203.0.113.0") == "203.0.113.x"
    assert filters.network("2001:db8:1::") == "2001:db8:1::/48"
    assert filters.network(None) == "-"
