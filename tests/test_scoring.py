"""Tests for the per-song performance score."""

from datetime import datetime, timedelta

from runnify.services.scoring import score_segment

START = datetime(2026, 10, 1, 7, 0, 0)


def _series(paces):
    """Timestamps one second apart for the given pace samples."""
    return [START + timedelta(seconds=i) for i in range(len(paces))]


def _segment(first, last):
    return {"start_time": START + timedelta(seconds=first), "end_time": START + timedelta(seconds=last)}


def test_returns_none_without_enough_samples():
    paces = [300.0] * 8
    assert score_segment(_segment(0, 7), _series(paces), paces) is None


def test_constant_pace_scores_fifty():
    paces = [300.0] * 30
    assert score_segment(_segment(0, 9), _series(paces), paces) == 50


def test_faster_song_scores_above_fifty_and_slower_below():
    paces = [300.0] * 10 + [270.0] * 10 + [330.0] * 10  # seconds per km: lower is faster
    timestamps = _series(paces)
    assert score_segment(_segment(10, 19), timestamps, paces) > 50
    assert score_segment(_segment(20, 29), timestamps, paces) < 50


def test_score_is_clamped_to_0_100():
    paces = [300.0] * 100 + [100.0] * 5
    score = score_segment(_segment(100, 104), _series(paces), paces)
    assert 0 <= score <= 100
