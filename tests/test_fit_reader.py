"""Runnify's own FIT reader gives exactly what fitparse gives, and leaves odd files to it."""

from datetime import datetime, timedelta

import pytest
from fitparse import FitParseError

from runnify.services import fit
from tests.fit_builder import FitWriter, build_fit, fit_time

START = datetime(2026, 10, 1, 7, 0)
USED = {  # the fields Runnify reads from records and laps
    "timestamp",
    "heart_rate",
    "cadence",
    "distance",
    "speed",
    "fractional_cadence",
    "enhanced_speed",
    "start_time",
    "total_elapsed_time",
    "intensity",
    "lap_trigger",
    "wkt_step_index",
}
# field number, size, base type
TIME, HEART, DISTANCE, SPEED = (253, 4, 0x86), (3, 1, 0x02), (5, 4, 0x86), (6, 2, 0x84)
CADENCE, FRACTION, ENHANCED = (4, 1, 0x02), (53, 1, 0x02), (73, 4, 0x86)
LATITUDE, NAME = (0, 4, 0x85), (100, 6, 0x07)


def _used(messages):
    return [{k: v for k, v in message.items() if k in USED} for message in messages]


def _same_as_fitparse(data):
    ours, theirs = fit._read_messages(data), fit._fitparse_messages(data)
    assert [_used(m) for m in ours] == [_used(m) for m in theirs]
    return ours


def _at(second):
    return fit_time(START + timedelta(seconds=second))


def test_a_watchs_records_and_laps_read_as_fitparse_reads_them():
    samples = [
        (
            START + timedelta(seconds=i),
            None if i % 9 == 0 else 150,
            3.1 * i,
            None if i % 13 else 3.1,
            85,
        )
        for i in range(300)
    ]
    laps = [
        (START, 100, 2, 0, None),
        (START + timedelta(seconds=100), 100, 4, 7, 1),
        (START + timedelta(seconds=200), 50, 6, 9, 4095),  # numbers fitparse doesn't name
        (START + timedelta(seconds=250), 50, 1, 8, 0xFFFF),
    ]
    records, read_laps = _same_as_fitparse(build_fit(samples, laps))
    assert len(records) == 300 and len(read_laps) == 4


def test_compressed_timestamps_roll_over_as_fitparse_rolls_them():
    writer = FitWriter()
    writer.define(0, 20, [TIME, HEART, SPEED])
    writer.define(1, 20, [HEART, SPEED])  # its time comes in the record header
    first = _at(0) | 0x1F  # the low five bits at their highest, so the next offset rolls over
    writer.data(0, first, 140, 3000)
    for offset in (1, 5, 30, 2):
        writer.data(1, 141, 3100, time_offset=offset)
    records, _ = _same_as_fitparse(writer.bytes())
    assert len({record["timestamp"] for record in records}) == 5


def test_big_endian_definitions_and_developer_fields():
    writer = FitWriter()
    # a Connect IQ data field describes itself first, as on a real watch
    writer.define(3, 207, [(1, 16, 0x0D), (3, 1, 0x02)])  # developer_data_id
    writer.data(3, tuple(range(16)), 0)
    writer.define(4, 206, [(0, 1, 0x02), (1, 1, 0x02), (2, 1, 0x02), (3, 16, 0x07)])
    writer.data(4, 0, 0, 0x84, b"Power")  # field_description
    writer.data(4, 0, 1, 0x86, b"Stride")
    writer.define(0, 20, [TIME, LATITUDE, HEART, DISTANCE, ENHANCED], big_endian=True)
    writer.define(2, 20, [TIME, HEART, NAME, CADENCE, FRACTION], developer=[(0, 2, 0), (1, 4, 0)])
    for second in range(20):
        writer.data(0, _at(second), 600_000_000, 150, 310 * second, 3100)
        writer.data(2, _at(second), 151, b"run", 86, 64)
    records, _ = _same_as_fitparse(writer.bytes())
    assert records[1]["cadence"] == 86 and records[1]["fractional_cadence"] == 0.5


@pytest.mark.parametrize("enhanced_first", [True, False])
@pytest.mark.parametrize(("speed", "enhanced"), [(3000, 3000), (None, 3000), (3000, None)])
def test_speed_and_enhanced_speed_together(enhanced_first, speed, enhanced):
    writer = FitWriter()
    fields = [TIME, ENHANCED, SPEED] if enhanced_first else [TIME, SPEED, ENHANCED]
    writer.define(0, 20, fields)
    values = (enhanced, speed) if enhanced_first else (speed, enhanced)
    writer.data(0, _at(0), *values)
    _same_as_fitparse(writer.bytes())


def test_a_local_message_redefined_halfway_and_chained_files():
    writer = FitWriter()
    writer.define(0, 20, [TIME, HEART])
    writer.data(0, _at(0), 140)
    writer.define(0, 19, [TIME, (2, 4, 0x86), (7, 4, 0x86), (23, 1, 0x00), (24, 1, 0x00)])
    writer.data(0, _at(60), _at(0), 60_000, 3, 0)
    writer.chain()
    writer.define(5, 20, [TIME, HEART, SPEED])
    writer.data(5, _at(61), 141, 2900)
    records, laps = _same_as_fitparse(writer.bytes())
    assert len(records) == 2 and laps[0]["intensity"] == "cooldown"


@pytest.mark.parametrize(
    "odd",
    [
        "compressed_speed_distance",  # old devices: fitparse expands and accumulates it
        "heart_rate_array",
        "relative_time",  # seconds since power-on
    ],
)
def test_odd_files_are_left_to_fitparse(odd):
    writer = FitWriter()
    if odd == "compressed_speed_distance":
        writer.define(0, 20, [TIME, HEART, (8, 3, 0x0D)])
        writer.data(0, _at(0), 150, (0x2C, 0x01, 0x00))
    elif odd == "heart_rate_array":
        writer.define(0, 20, [TIME, (3, 2, 0x02)])
        writer.data(0, _at(0), (150, 151))
    else:
        writer.define(0, 20, [TIME, HEART])
        writer.data(0, 1000, 150)
    data = writer.bytes()
    with pytest.raises(fit._Unusual):
        fit._read_messages(data)
    assert fit._fitparse_messages(data)  # and fitparse reads it


def test_parse_fit_reads_a_watchs_file_without_fitparse(monkeypatch):
    def unused(data):
        raise AssertionError("fitparse wasn't needed")

    monkeypatch.setattr(fit, "_fitparse_messages", unused)
    data = build_fit([(START + timedelta(seconds=i), 150, 3.0 * i, 3.0, 85) for i in range(60)])
    assert len(fit.parse_fit(data)) == 60


def test_parse_fit_falls_back_to_fitparse_for_an_old_devices_file():
    writer = FitWriter()
    writer.define(0, 20, [TIME, HEART, SPEED, (8, 3, 0x0D)])
    for second in range(30):
        writer.data(0, _at(second), 150, 3000, (0x2C, 0x01, 0x00))
    series = fit.parse_fit(writer.bytes())
    assert len(series) == 30 and series.heart_rates[0] == 150


def test_broken_files_fail_as_they_did():
    data = build_fit([(START + timedelta(seconds=i), 150, 3.0 * i, 3.0) for i in range(60)])
    with pytest.raises(FitParseError):
        fit.parse_fit(data[: len(data) // 2])
