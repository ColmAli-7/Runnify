"""Per-song performance scoring."""

from statistics import mean, pstdev


def score_segment(seg, timestamps, pace_s_per_km, hr=None):
    """Score how fast the user ran during one song relative to the whole run.

    ``score = 50 + 20 * z`` where ``z = (run_avg_pace - song_avg_pace) /
    run_pace_std``, clamped to 0-100. 50 is average pace for the run; higher
    is faster. See ``docs/scoring.md``.

    Args:
        seg: Dict with ``start_time`` and ``end_time`` of the song segment.
        timestamps: Run timestamps from the FIT file.
        pace_s_per_km: Pace samples (seconds per km) aligned with ``timestamps``.
        hr: Heart-rate samples (currently unused).

    Returns:
        The score rounded to 1 decimal place, or ``None`` if there are fewer
        than 5 pace samples in the segment or 10 in the run.
    """
    song_paces = [
        pace
        for t, pace in zip(timestamps, pace_s_per_km, strict=False)
        if pace is not None and seg["start_time"] <= t <= seg["end_time"]
    ]  # paces during song segment
    run_paces = [pace for pace in pace_s_per_km if pace is not None]  # all valid paces
    if len(song_paces) < 5 or len(run_paces) < 10:
        return None  # skip if not enough data
    run_avg_pace = mean(run_paces)
    run_std_pace = pstdev(run_paces) if len(run_paces) > 1 else 0
    song_avg_pace = mean(song_paces)
    # how many standard deviations faster than the run average the song was
    z_score = 0 if run_std_pace == 0 else (run_avg_pace - song_avg_pace) / run_std_pace
    score = 50 + 20 * z_score  # scale to the 0-100 range
    return round(max(0, min(100, score)), 1)
