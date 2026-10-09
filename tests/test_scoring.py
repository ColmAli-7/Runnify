"""The per-song effect: local baseline, robust statistics, stops ignored."""

from datetime import datetime, timedelta

from runnify.services.fit import Series
from runnify.services.scoring import song_effect

START = datetime(2026, 10, 1, 7, 0, 0)


def _series(paces, heart_rates=None):
    return Series(
        timestamps=[START + timedelta(seconds=i) for i in range(len(paces))],
        heart_rates=heart_rates or [150] * len(paces),
        paces=paces,
    )


def _at(second):
    return START + timedelta(seconds=second)


def test_not_enough_samples_gives_no_score():
    effect = song_effect(_series([300.0] * 40), _at(0), _at(10))
    assert effect.score is None


def test_steady_pace_scores_fifty():
    effect = song_effect(_series([300.0] * 900), _at(300), _at(480))
    assert effect.score == 50.0 and effect.pace_delta == 0.0


def test_a_song_that_lifts_the_pace_scores_above_fifty_with_the_lift_in_seconds():
    paces = [300.0] * 300 + [290.0] * 180 + [300.0] * 300
    effect = song_effect(_series(paces), _at(300), _at(479))
    assert effect.pace_delta == 10.0
    assert effect.score > 50


def test_a_slower_song_scores_below_fifty():
    paces = [300.0] * 300 + [312.0] * 180 + [300.0] * 300
    assert song_effect(_series(paces), _at(300), _at(479)).score < 50


def test_the_baseline_is_local_so_a_slow_warm_up_does_not_flatter_later_songs():
    # a slow first 15 minutes, then a steady 5:00/km; the song plays during the steady part
    paces = [360.0] * 900 + [300.0] * 900
    effect = song_effect(_series(paces), _at(1200), _at(1380))
    assert effect.pace_delta == 0.0  # it was no faster than the running around it


def test_stops_inside_a_song_are_ignored():
    paces = [300.0] * 300 + [290.0] * 90 + [None] * 60 + [290.0] * 90 + [300.0] * 300
    effect = song_effect(_series(paces), _at(300), _at(539))
    assert effect.pace_delta == 10.0
    assert effect.seconds == 180


def test_heart_rate_change_and_position_are_reported():
    paces = [300.0] * 900
    heart_rates = [150] * 300 + [158] * 180 + [150] * 420
    effect = song_effect(_series(paces, heart_rates), _at(300), _at(479))
    assert effect.hr_delta == 8.0
    assert effect.position == round(300 / 899, 3)


def test_scores_are_clamped():
    paces = [300.0] * 300 + [200.0] * 120 + [300.0] * 300
    assert song_effect(_series(paces), _at(300), _at(419)).score == 100.0
