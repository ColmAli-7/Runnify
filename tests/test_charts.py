"""Chart geometry: percentages a plain SVG can draw at any size."""

import pytest

from runnify.services.charts import BOX, bar_chart, run_chart


def _points(line):
    return [tuple(map(float, pair.split(","))) for pair in line.split()]


def test_faster_running_is_drawn_higher():
    paces = [330.0] * 300 + [270.0] * 300  # a 10-minute run that speeds up halfway
    chart = run_chart(paces)
    (line,) = chart.lines
    points = _points(line)
    assert points[-1][1] < points[0][1]  # smaller y is higher up
    assert all(0 <= x <= BOX and 0 <= y <= BOX for x, y in points)


def test_a_stop_splits_the_line():
    paces = [300.0] * 200 + [None] * 60 + [300.0] * 200
    chart = run_chart(paces, points=46)
    assert len(chart.lines) == 2


def test_too_little_movement_gives_an_empty_chart():
    assert run_chart([None] * 100).empty
    assert run_chart([]).empty
    assert not run_chart([300.0, 301.0, 299.0]).empty


def test_song_bands_are_placed_by_time():
    paces = [300.0 + (i % 7) for i in range(601)]  # ten minutes
    chart = run_chart(paces, songs=[(60, 120, "Song", "best"), (590, 900, "Cut off", "normal")])
    first, last = chart.bands
    assert (first.x, first.width, first.kind, first.label) == (10.0, 10.0, "best", "Song")
    assert last.x + last.width == pytest.approx(100.0)  # clipped at the finish
    assert (first.start, first.end) == (60, 120)


def test_axis_labels():
    paces = [270.0 + (i % 60) for i in range(1800)]  # half an hour between 4:30 and 5:29
    chart = run_chart(paces)
    assert [label for _, label in chart.x_ticks] == ["5:00", "10:00", "15:00", "20:00", "25:00"]
    assert all(0 < y < 100 for y, _ in chart.y_ticks)
    labels = [label for _, label in chart.y_ticks]
    assert labels == sorted(labels)  # faster paces (smaller numbers) at the top
    assert all(":" in label for label in labels)


def test_long_runs_get_hour_labels():
    chart = run_chart([300.0 + (i % 9) for i in range(2 * 3600)])
    assert chart.x_ticks[-1][1] == "1:40:00"
    assert len(chart.x_ticks) <= 6


def test_bars_fill_the_height_below_the_headroom():
    chart = bar_chart(
        [("Mon", 5.0), ("Tue", 10.0), ("Wed", None)], value_format=lambda v: f"{v:g} km"
    )
    mon, tue, wed = chart.bars
    assert tue.y == 14.0 and tue.bottom == 100.0
    assert mon.height == pytest.approx(tue.height / 2)
    assert wed.kind == "muted" and wed.value_label == ""
    assert tue.value_label == "10 km"
    assert mon.center < tue.center < wed.center
    assert not chart.empty


def test_diverging_bars_grow_both_ways_from_the_middle():
    chart = bar_chart([("Start", -4.0), ("Finish", 8.0)], diverging=True)
    start, finish = chart.bars
    assert chart.baseline == 50.0
    assert start.kind == "down" and start.y == 50.0
    assert finish.kind == "up" and finish.bottom == 50.0
    assert finish.height == pytest.approx(2 * start.height)


def test_no_values_means_an_empty_chart():
    assert bar_chart([]).bars == []
    assert bar_chart([("Mon", None)]).empty
