# Matching, measuring and ranking songs

How Runnify decides which songs played during a run, how it measures each
song's effect on your pace, and how those measurements become insights and
playlists. Method version: **2** (`services/scoring.METHOD_VERSION`).

## 1. Inputs

**Runs** come from Garmin. Each has a start time, a duration and a stream of
samples, one per second: pace in seconds per km and heart rate. While you are
stopped (slower than 15:00/km) or the GPS glitches (faster than 2:00/km) a
sample carries no pace (`services/fit.py`).

**Plays** come from Spotify's extended streaming history
(`Streaming_History_Audio_*.json` inside the zip):

| Field | Meaning |
|---|---|
| `ts` | When playback **stopped** (UTC) |
| `ms_played` | How long the track played |
| `spotify_track_uri` | `spotify:track:<id>`; rows without one are ignored |
| `master_metadata_track_name`, `master_metadata_album_artist_name` | Names |
| `episode_*` fields | Present for podcasts and videos, which are ignored |
| `skipped`, `reason_end` | Whether the play was skipped |

## 2. Matching plays to runs

```text
play = [ts - ms_played, ts)
```

The play is intersected with every run. Each overlap of at least
`HISTORY_MIN_OVERLAP_SECONDS` is stored with `played_at` set to the start of the
overlap and `time_played` to its length, so a song that started before the run
only counts for the part you were running (`services/history_import.py`).
Plays that never overlap a run are not stored.

## 3. Measuring one song: the effect

`services/scoring.song_effect(series, start, end)` compares the song with
**your own pace in the five minutes before and after it, in the same run**.

```text
inside  = moving pace samples while the song played
context = moving pace samples in the 5 minutes either side
pace_delta = median(context) - median(inside)        # s/km; positive = faster during the song
hr_delta   = median(heart rate inside) - median(heart rate in context)
```

- **Local context, not the run average.** A whole-run average blames the music
  for the warm-up, the hills and the late-race fade. The minutes around the
  song share most of those conditions, so they mostly cancel out.
- **Robust statistics.** Medians are not swung by a single GPS spike.
- **Stops are left out.** Samples without pace are ignored, so waiting at a
  crossing never reads as slow running.
- **Enough evidence or nothing.** A song needs about 20 seconds of moving
  samples (`MIN_SONG_SAMPLES`) and its context about 30 (`MIN_CONTEXT_SAMPLES`).
  When a song sits at the very start or end of a run and the context is too
  thin, the rest of the run stands in for it. Otherwise no effect is stored.
- **Position.** Where the song started, from 0 (start) to 1 (finish), is kept
  for the phase analysis below.

A 0 to 100 `score` is also stored for older views: 50 is your usual pace at that
point in the run and each robust standard deviation faster adds 20 points
(the spread is the median absolute deviation, scaled, with a floor of 5 s/km).
Pages show `pace_delta` instead, as "+9 s/km", because it means something to a
runner.

Effects are computed once and stored in `run_song_analysis`
(`services/analysis.rescore_run`), when a run's stream arrives and after each
history import. When the method improves, `flask --app runnify scores rebuild`
re-measures every run.

## 4. A run's results

`services/results.run_results` lists every play during a run in playing order,
ranks the measured ones by `pace_delta`, marks the fastest and slowest, and says
why any play has no result ("Skipped", or too little running to measure). This
is the run page's results table and the dashboard's latest run.

## 5. Across runs: insights

`services/insights.py` aggregates the stored effects for a date range
(30 days, 90 days, this year or all time).

**A song's lift** is the mean of its per-play effects, weighted by the seconds
measured. It is then **shrunk** towards zero as if the song had also played on
`PRIOR_PLAYS` (2) runs with no effect at all:

```text
shrunk_lift = lift * plays / (plays + 2)
```

so a song that helped once by 30 s/km (shrunk to 10) can't outrank one that
helped by 12 s/km on ten runs (shrunk to 10 too, with far more evidence behind
it). Rankings need at least two plays (`MIN_PLAYS_TO_RANK`), and every finding
shows how many runs it rests on. Confidence is "high" from five plays.

| Finding | How |
|---|---|
| Power songs | The five largest positive shrunk lifts |
| Drag songs | The five largest negative shrunk lifts |
| Top artists | The same, grouping every song by an artist |
| Heart raisers | Songs with two or more plays that raised heart rate, the biggest rise first |
| Most skipped | Songs skipped most often during runs |
| With and without music | Average pace of whole runs that had matched songs, and of those that didn't (a rough guide: you may run different sessions with and without music) |
| Where songs work hardest | See below |

### Where songs work hardest

A plain average of effects by part of the run (start, middle, finish) mostly
measures the warm-up: every early song is compared with faster running after
it, so the start always looks bad. Instead, for each play of a song heard more
than once, Runnify compares the play's effect with **the same song's average on
its other plays**, and fits the slope of that relationship within each part of
the run:

```text
strength(phase) = slope of play effect against the song's usual effect, plays in that phase
```

A strength of 1 means songs worked as strongly as usual there; 1.5 means half
as much again; 0.5 means half as much. A shift that hits every song alike, such
as a slow first kilometre, changes the intercept and not the slope, so it no
longer distorts the answer. Each phase needs 30 plays of repeated songs
(`MIN_PHASE_PLAYS`) before it is shown. The start is the first fifth of a run
and the finish the last fifth.

## 6. Playlists

`services/playlists.plan` chooses songs with at least two plays (or one, when
"include songs heard on only one run" is ticked) and a positive shrunk lift
(easy runs also accept songs within 1 s/km of neutral), strongest first, until
the target length is filled, then orders them for the session (`arrange`):

| Session | Order |
|---|---|
| Easy run | Strong songs spread out, and songs that raise heart rate ranked lower (half a s/km per bpm) |
| Tempo run | Builds: weakest first, strongest last |
| Long run | Steady in the middle, with the strongest songs held back for the final stretch |
| Race | Strong throughout, the very best two saved for the finish |
| Intervals | Alternates the hardest-working songs (efforts) with calmer ones (recoveries) |

Songs are never repeated. When the proven songs can't fill the time, the
playlist is shorter and says why. Track lengths are learned from plays that ran
to the end; unknown lengths count as 3.5 minutes.

## 7. Checking the method end to end

`flask --app runnify demo seed` simulates four months of runs second by second
(warm-up, hills, fatigue, traffic-light stops, noise) with songs whose true
effects are known, and whose effects grow later in a run. The real pipeline
then has to find them: `tests/test_demo.py` checks that the known boosters and
draggers come out on top, and the demo's insights show the late-run pattern.
