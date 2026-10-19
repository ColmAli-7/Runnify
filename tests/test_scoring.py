"""The per-song effect: local baseline, robust statistics, stops ignored, like against like,
and extra effort charged."""

from datetime import datetime, timedelta

from runnify.services.fit import Series
from runnify.services.laps import Lap, kinds_by_second
from runnify.services.scoring import song_effect

START = datetime(2026, 10, 1, 7, 0, 0)


def _series(paces, heart_rates=None, cadences=None):
    return Series(
        timestamps=[START + timedelta(seconds=i) for i in range(len(paces))],
        heart_rates=heart_rates or [150] * len(paces),
        paces=paces,
        cadences=cadences or [],
    )


def _steps(*blocks):
    """One value a second from ``(seconds, value)`` blocks."""
    return [value for seconds, value in blocks for _ in range(seconds)]


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


def _lifted(song_pace, song_hr, cadences=None):
    """A steady 15 minutes at 5:00/km and 150 bpm, with a song from minute 5 to minute 8.

    Heart rate trails the effort, so the song's heart rate is set 20 seconds late.
    """
    paces = _steps((300, 300.0), (180, song_pace), (420, 300.0))
    heart_rates = _steps((320, 150), (180, song_hr), (400, 150))
    return song_effect(_series(paces, heart_rates, cadences), _at(300), _at(479))


def test_a_lift_that_costs_the_usual_heart_rate_is_kept():
    effect = _lifted(290.0, 153)  # 10 s/km faster costs about 3 bpm at 5:00/km and 150 bpm
    assert (effect.pace_delta, effect.effort_charge, effect.hr_delta) == (10.0, 0.0, 3.0)


def test_a_lift_bought_only_with_extra_effort_is_lost():
    effect = _lifted(290.0, 158)
    assert (effect.pace_delta, effect.effort_charge) == (0.0, 10.0)  # never below zero


def test_part_of_a_lift_is_charged_for_part_of_the_extra_effort():
    effect = _lifted(290.0, 156)  # 3 bpm beyond the cost of the speed, 2 of them forgiven
    assert (effect.pace_delta, effect.effort_charge) == (6.7, 3.3)


def test_a_slower_song_is_left_as_measured():
    effect = _lifted(320.0, 158)  # uphill, say: the slowdown already counts against it
    assert (effect.pace_delta, effect.effort_charge) == (-20.0, None)


def test_heart_rate_locked_onto_the_cadence_is_ignored():
    effect = _lifted(290.0, 170, cadences=[170] * 900)  # a wrist sensor counting steps
    assert (effect.pace_delta, effect.hr_delta, effect.effort_charge) == (10.0, None, None)


def _intervals(rep=180, jog=120, reps=5):
    """10 minutes at 5:30/km, reps at 4:15/km with jogs at 6:00/km, 10 minutes at 5:45/km."""
    blocks, laps, second = [(600, 330.0)], [Lap(0, 600, "warmup")], 600
    for _ in range(reps):
        blocks += [(rep, 255.0), (jog, 360.0)]
        laps += [Lap(second, second + rep, "hard"), Lap(second + rep, second + rep + jog, "jog")]
        second += rep + jog
    blocks.append((600, 345.0))
    laps.append(Lap(second, second + 600, "cooldown"))
    paces = _steps(*blocks)
    return _series(paces), kinds_by_second(laps, len(paces))


def test_songs_are_measured_against_the_same_kind_of_running():
    series, kinds = _intervals()
    in_a_rep = song_effect(series, _at(1210), _at(1370), kinds)  # the third rep
    assert (in_a_rep.pace_delta, in_a_rep.lap_kind) == (0.0, "hard")
    assert in_a_rep.effort_charge is None  # heart rate never settles inside a rep
    in_a_jog = song_effect(series, _at(1390), _at(1490), kinds)
    assert (in_a_jog.pace_delta, in_a_jog.lap_kind) == (0.0, "jog")
    # against everything around it, mostly reps, the same jog reads as a huge drag
    assert song_effect(series, _at(1390), _at(1490)).pace_delta < -50


def test_a_song_across_a_lap_edge_is_measured_on_its_main_lap():
    series, kinds = _intervals()
    effect = song_effect(series, _at(1185), _at(1365), kinds)  # comes on 15 s before the rep
    assert (effect.pace_delta, effect.lap_kind) == (0.0, "hard")
    assert effect.seconds == 1365 - 1210 + 1  # without the jog or the rep's first 10 seconds


def test_a_rep_with_no_others_nearby_is_compared_with_the_runs_other_reps():
    series, kinds = _intervals(rep=360, jog=360, reps=3)
    effect = song_effect(series, _at(1340), _at(1660), kinds)  # in the second 6-minute rep
    assert (effect.pace_delta, effect.lap_kind) == (0.0, "hard")


def test_walks_never_count():
    paces = _steps((600, 300.0), (240, 660.0), (600, 300.0))
    kinds = kinds_by_second(
        [Lap(0, 600, "steady"), Lap(600, 840, "walk"), Lap(840, 1440, "steady")], len(paces)
    )
    assert song_effect(_series(paces), _at(620), _at(820), kinds).score is None
