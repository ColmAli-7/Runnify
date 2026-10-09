# Matching and scoring

This document explains how Runnify decides which songs were playing during a
run, and how it turns that into a per-song **performance score**.

## 1. Inputs

### Garmin runs

Each `Run` has a start time (`date_time`, UTC) and a `duration` in seconds,
which together give the run interval `[start, start + duration)`. The run's
`.fit` file provides second-by-second records.

### Spotify extended streaming history

The `my_spotify_data.zip` export contains JSON arrays of plays
(`Streaming_History_Audio_*.json`). The fields Runnify uses are:

| Field | Meaning |
|---|---|
| `ts` | When playback **stopped** (UTC) |
| `ms_played` | How long the track played, in milliseconds |
| `spotify_track_uri` | `spotify:track:<id>`; rows without it are skipped |
| `master_metadata_track_name`, `master_metadata_album_artist_name` | Track and artist names |
| `episode_name`, `episode_show_name`, `spotify_episode_uri` | Present for podcasts and videos; those rows are skipped |

## 2. Matching plays to runs

For every music play:

```text
play_start = ts - ms_played
play_end   = ts
```

The play is intersected with every run interval. Each non-empty overlap of at
least `HISTORY_MIN_OVERLAP_SECONDS` (default 1 s) is stored as a
`UserSongHistory` row, where `played_at` is the overlap start and
`time_played` is the overlap length in seconds. A play that spans the start or
end of a run is therefore trimmed to the part that happened while running.

Implementation: `services/history_import.py`.

## 3. Building the pace series

`services/fit.read_fit_to_series` reads every `record` message from the FIT file:

1. Take `enhanced_speed` (or `speed`) in m/s and convert it to pace:
   `pace = 1000 / speed` seconds per km.
2. If speed is missing, derive it from the change in `distance` since the
   previous record. Changes under 0.5 m are ignored as GPS noise.
3. Smooth the series with an **exponential moving average** (`alpha = 0.2`):
   `ema = 0.2 * value + 0.8 * previous_ema`. Gaps carry the previous value forward.

The function returns timestamps, heart rates and smoothed paces.

## 4. The performance score

Implemented in `services/scoring.score_segment`.

For a song segment `[start_time, end_time]` within a run:

```text
song_paces = pace samples whose timestamp falls inside the segment
run_paces  = all pace samples in the run

z     = (mean(run_paces) - mean(song_paces)) / pstdev(run_paces)
score = clamp(50 + 20 * z, 0, 100)        # rounded to 1 decimal place
```

- Pace is seconds per km, so **lower is faster**. A song where you ran faster
  than your run average gives a positive `z` and a score **above 50**.
- **50** = exactly your average pace for that run.
- Each standard deviation faster or slower moves the score by **20 points**.
  ±2.5 standard deviations hits the 100 or 0 cap.
- If the run's pace never varies (`pstdev == 0`), the score is 50.
- No score is produced (`None`) if the segment has fewer than **5** pace
  samples or the run has fewer than **10**.

Because the score is relative to *that run's* own average, it measures how a
song changed your effort within a run. It is comparable across easy and hard
runs, but it is not an absolute speed measure.

Heart rate is passed to the scoring function but is not yet used.

## 5. Where scores appear

- **Run analysis** (`/activity/<id>`): scores are calculated live for each
  song segment and drawn over the pace/HR chart.
- **Upload**: after a history import, a score is stored in `run_song_analysis` for every matched play.
- **Music Insights** (`/music-insights`): averages the stored scores per song
  and per month, for best song, top-10 tables and trend charts.
