"""Chart geometry: percentages a plain SVG can draw at any size."""

from datetime import datetime

import pytest

from runnify.services.charts import BOX, bar_chart, heart_chart, matched_chart, run_chart


def _points(line):
    return [tuple(map(float, pair.split(","))) for pair in line.split()]


def test_faster_running_is_drawn_higher():
    paces = [330.0] * 300 + [270.0] * 300  # a 10-minute run that speeds up halfway
    chart = run_chart(paces)
    (line,) = chart.lines
    points = _points(line)
    assert points[-1][1] < points[0][1]  # smaller y is higher up
    assert all(0 <= x <= BOX and 0 <= y <= BOX for x, y in points)


def test_a_higher_heart_rate_is_drawn_higher():
    rates = [140] * 300 + [170] * 300
    chart = heart_chart(rates)
    points = _points(chart.lines[0])
    assert points[-1][1] < points[0][1]
    assert chart.top > chart.bottom
    labels = [int(label) for _, label in chart.y_ticks]
    assert labels == sorted(labels, reverse=True)  # the highest rate at the top


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


def test_matched_runs_are_placed_by_date_and_lift():
    chart = matched_chart(
        [
            (datetime(2026, 7, 1, 6, 30), 12.0, "First run"),
            (datetime(2026, 8, 1, 19, 15), -6.0, "Second run"),  # the hour doesn't move a dot
            (datetime(2026, 9, 1, 12, 0), 0.4, "Third run"),
        ],
        trend=(8.0, -2.0),
    )
    first, second, third = chart.dots
    assert first.x < second.x < third.x
    assert second.x == pytest.approx(50.0)  # 31 days after the first and 31 before the last
    assert chart.zero == 50.0
    assert first.y < chart.zero < second.y  # faster above the zero line, slower below it
    assert (first.kind, second.kind, third.kind) == ("up", "down", "flat")
    assert first.label == "First run"
    assert (chart.trend.x1, chart.trend.x2) == (first.x, third.x)
    assert chart.trend.y1 < chart.zero < chart.trend.y2


def test_the_lift_axis_gives_faster_and_slower_the_same_room():
    chart = matched_chart([(datetime(2026, 7, 1), 23.0, "a"), (datetime(2026, 7, 8), -4.0, "b")])
    labels = " ".join(label for _, label in chart.y_ticks)
    assert labels == "+30 +20 +10 0 \u221210 \u221220 \u221230"
    assert [y for y, _ in chart.y_ticks][::3] == [0.0, 50.0, 100.0]
    small = matched_chart([(datetime(2026, 7, 1), 0.5, "a")])
    assert " ".join(label for _, label in small.y_ticks) == "+10 +5 0 \u22125 \u221210"


def test_dates_are_labelled_by_month_over_a_season_and_by_day_over_a_few_days():
    season = matched_chart([(datetime(2026, 6, 18), 1.0, "a"), (datetime(2026, 10, 2), 1.0, "b")])
    assert [label for _, label in season.x_ticks] == ["Jul", "Aug", "Sep", "Oct"]
    days = matched_chart(
        [(datetime(2026, 10, 5, 7), 1.0, "a"), (datetime(2026, 10, 7, 18), 1.0, "b")]
    )
    assert [label for _, label in days.x_ticks] == ["5 Oct", "6 Oct", "7 Oct"]
    assert days.x_ticks[0][0] == days.dots[0].x  # a day's label sits under its runs
    new_year = matched_chart([(datetime(2026, 11, 20), 1.0, "a"), (datetime(2027, 3, 1), 1.0, "b")])
    assert [label for _, label in new_year.x_ticks] == ["Dec", "Jan 2027", "Feb", "Mar"]
    years = matched_chart([(datetime(2025, 11, 3), 1.0, "a"), (datetime(2028, 10, 1), 1.0, "b")])
    assert len(years.x_ticks) <= 6
    assert years.x_ticks[0][1] == "Jan 2026"


def test_plays_on_one_day_sit_in_the_middle_without_a_trend():
    chart = matched_chart(
        [(datetime(2026, 10, 5, 7), 9.0, "a"), (datetime(2026, 10, 5, 19), -3.0, "b")],
        trend=(9.0, -3.0),
    )
    assert [dot.x for dot in chart.dots] == [50.0, 50.0]
    assert chart.x_ticks == [(50.0, "5 Oct")]
    assert chart.trend is None


def test_no_plays_means_an_empty_matched_chart():
    assert matched_chart([]).empty
