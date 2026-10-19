# Matching, measuring and ranking songs

How Runnify decides which songs played during a run, how it cuts a run into
laps, how it measures each song's effect on your pace, and how those
measurements become insights and playlists. Method version: **3**
(`services/scoring.METHOD_VERSION`).

## 1. Inputs

**Runs** come from Garmin. Each has a start time, a duration and a stream of
samples, one a second: pace in seconds per km, heart rate, and cadence (steps
a minute) and distance when the watch recorded them. While you are stopped
(slower than 15:00/km) or the GPS glitches (faster than 2:00/km) a sample
carries no pace. A watch on "smart" recording writes a record every few
seconds: gaps of up to 10 seconds carry the last record's values, and longer
ones (auto-pause) count as stopped (`services/fit.at_one_hertz`). The stream
also keeps the watch's own laps: when each started and ended, its intensity
(warm-up, active, rest, recovery, cool-down) and what ended it (the lap
button, a distance, a time).

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

## 3. Laps and the kind of run

Not every run is one steady effort, so every run is cut into laps, each one
kind of running: **warm-up, hard, steady, jog, walk or cool-down**
(`services/laps.py`).

**The watch's laps** are used when they describe the session: a structured
workout (laps marked warm-up, rest, recovery or cool-down, or tied to workout
steps), or laps you ended with the lap button whose paces clearly fall into
fast and slow. In a workout, work steps between jogged recoveries are hard;
without jogs (a run-walk, or Garmin's suggested easy runs with a warm-up and
cool-down) a work step is hard only when clearly quicker than the warm-up or
than your usual pace. With lap-button laps, heart rate decides which laps were
the efforts when it disagrees with pace, so hill reps (slow but hard) come out
right. Laps the watch ends by itself every kilometre or mile are ignored.

**Otherwise the laps are read from the run:**

1. Each second is running, walking or stopped, judged on a 31-second rolling
   median of speed: walking is slower than 9:00/km, or under 140 steps a minute
   when the watch counted steps (so a brisk walk isn't taken for a slow jog).
2. Running is split into fast and slow stretches at the speed that separates
   them best (Otsu's method), with a little hysteresis; stretches under 30
   seconds join a neighbour.
3. That counts as a session only when fast running is at least 15% quicker
   than slow running, there are two or more fast stretches or one tempo block
   of eight minutes or more, and, when heart rate exists, the fast stretches
   run at least 3 bpm hotter, 20 seconds later (heart rate lags). Uphill running
   is slow but hard, so this keeps a hilly steady run steady.
4. Walks of 30 seconds or more are their own laps in every run; a stop at the
   lights stays part of the lap around it.
5. Slow running of three minutes or more before the first effort and after the
   last is the warm-up and the cool-down; fast stretches are hard and the rest
   are jogs. A run with no session is one steady lap.

**The kind of run** follows from the laps: three or more similar reps
(lengths within 35% of their mean) are **intervals** and uneven efforts a
**fartlek**; one or two hard blocks of eight minutes or more make a **tempo
run**; running between walks, with a tenth or more of the run walked, is a
**run-walk**. A run with no efforts is **long** from 75 minutes or 15 km, a
**tempo run** when it is clearly quicker (7%) than your usual pace (the median
over your other runs, once there are three), and otherwise **easy**. A
**race** is only ever your call. Types are worked out again after every sync
and import, since a first sync stores the newest runs before there is a usual
pace to judge them by.

**You can change both** on the run's page: the kind of run, each lap's kind,
joining or splitting laps, or typing the workout ("15 min warm-up, 6 x 3 min
hard with 2 min jog, 10 min cool-down"). A typed workout is placed step by step
along the run, each change snapped to the biggest real change in pace nearby,
so a rep that ran long doesn't push the rest out of line
(`services/workouts.py`). Only the steps Runnify reads are kept, written back
plainly, never the text as typed. Laps and types you set are never worked out
again unless you ask.

## 4. Measuring one song: the effect

`services/scoring.song_effect(series, start, end, kinds)` compares the song with
**your own pace on the same kind of running, in the five minutes before and
after it, in the same run**.

```text
inside      = moving samples of the song's main kind of lap, lap edges left out
context     = moving samples of that kind in the 5 minutes either side
              (or the run's other laps of that kind, when too few are near)
pace_change = median(context) - median(inside)      # s/km; positive = faster during the song
hr_delta    = median(heart rate inside) - median(heart rate in context), both 20 s later
```

- **Local context, not the run average.** A whole-run average blames the music
  for the warm-up, the hills and the late-race fade. The minutes around the
  song share most of those conditions, so they mostly cancel out.
- **Like against like.** A song during a hard rep is compared with your other
  reps, one during a jog with your other jogs. Against everything around it, a
  rep looks like a huge lift and a jog like a huge drag, whatever the music did.
  The song is measured on whichever kind of lap most of it fell in; walks never
  count, and the first and last 10 seconds of each lap (the change of pace
  itself) are left out. A steady run is one steady lap, so its songs are
  measured as before.
- **Robust statistics.** Medians are not swung by a single GPS spike.
- **Stops are left out.** Samples without pace are ignored, so waiting at a
  crossing never reads as slow running.
- **Enough evidence or nothing.** A song needs about 20 seconds of moving
  samples (`MIN_SONG_SAMPLES`) and its context about 30 (`MIN_CONTEXT_SAMPLES`).
  When a song sits at the very start or end of a run and the context is too
  thin, the rest of the run's laps of that kind stand in for it. Otherwise no
  effect is stored.
- **Heart rate as it is.** Heart rate trails the effort, so it is read 20
  seconds late (`HR_LAG`), and samples that match the cadence to within 3 are
  ignored: a wrist sensor locked onto your steps.
- **Position.** Where the song started, from 0 (start) to 1 (finish), is kept
  for the phase analysis below.

**Extra effort is charged.** Running faster costs heart rate, about 2 to 3 bpm
for every 10 s/km. A song that lifts your pace keeps its lift when your heart
rate rose by about that much; any rise beyond what the extra speed explains
comes off the lift:

```text
cost       = min(context pace / (context heart rate - 60), 4)   # s/km per bpm
extra      = hr_delta - pace_change / cost - 2                   # bpm beyond the cost of the speed
charge     = min(max(extra, 0) * cost, pace_change)
pace_delta = pace_change - charge                                # the lift every page shows
```

The 2 bpm is an allowance for heart-rate noise, and the cap of 4 s/km per bpm
keeps slow running from magnifying it. The charge applies on steady running
only (inside reps and recoveries heart rate is still climbing or falling), and
only when the song lifted your pace: a song that lifts it only by working
harder loses that lift, down to no effect, while slower songs are left as
measured, so a hill isn't counted twice. Without heart rate there is no charge.
The resting heart rate of 60 is assumed, not measured.

A 0 to 100 `score` is also stored for older views: 50 is your usual pace at that
point in the run and each robust standard deviation faster adds 20 points
(the spread is the median absolute deviation, scaled, with a floor of 5 s/km).
Pages show `pace_delta` instead, as "+9 s/km", because it means something to a
runner.

Effects are computed once and stored in `run_song_analysis`
(`services/analysis.rescore_run`) with the kind of lap each was measured on and
the charge, when a run's stream arrives, after each history import and after
you change a run's laps. When the method improves,
`flask --app runnify scores rebuild` works out every run's laps again (keeping
any you set) and re-measures it.

## 5. A run's results

`services/results.run_results` lists every play during a run in playing order,
ranks the measured ones by `pace_delta`, marks the fastest and slowest, and says
why any play has no result ("Skipped", or too little running to measure). On a
run with more than one kind of lap, each song is tagged with the kind it was
measured on. This is the run page's results table and the dashboard's latest
run.

## 6. Across runs: insights

`services/insights.py` aggregates the stored effects for a date range
(30 days, 90 days, this year or all time) and a kind of running: all running,
**hard efforts** (hard laps), **steady running** (steady laps) or
**recoveries** (jogs). Warm-ups and cool-downs count only in all running.

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
| Power songs | The five largest positive shrunk lifts, on the chosen kind of running |
| Drag songs | The five largest negative shrunk lifts, on the chosen kind of running |
| Top artists | The same, grouping every song by an artist |
| Heart raisers | Songs with two or more plays that raised heart rate, the biggest rise first |
| Most skipped | The five songs skipped most often during your runs in the range, counted over every play, measured or not, so a skip that left too little running to measure still counts. The figure is skips out of all those plays (on All time, the same numbers as the song's page), and a tie goes to the song heard more often. Always across all running, since a skip has no one kind of lap |
| With and without music | Average pace of whole runs that had matched songs, and of those that didn't (a rough guide: you may run different sessions with and without music). Always across all running |
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

### One song's page

`services/songs.py` gathers every play of one song during your runs, measured
or not, so skips count even when a skip left too little running to measure.
Its lift, evidence and rank are the same all-time aggregate the rankings use.
A song that can't rank yet says how many more measured plays it needs. A song
measured on more than one kind of running also shows its lift on each, from
its own plays.

Each measured play is a dot at its run's date. Once there are three
(`MIN_TREND_PLAYS`) on different days, a trend line is fitted through them by
least squares, weighted by the seconds measured like the lift itself. The page
only calls the line a trend when it rests on eight or more plays and its slope
is at least three standard errors from level (`CLEAR_TREND`), which the plays'
own ups and downs produce by chance less than one time in forty. Otherwise it
says the plays vary too much to call.

## 7. Playlists

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
| Intervals | Starts from the songs proven on hard efforts (on their lift there), then the rest; alternates the hardest-working songs (efforts) with calmer ones (recoveries). With none proven on hard efforts yet, it uses all running and says so |

Songs are never repeated. When the proven songs can't fill the time, the
playlist is shorter and says why. Track lengths are learned from plays that ran
to the end; unknown lengths count as 3.5 minutes.

## 8. Checking the method end to end

`flask --app runnify demo seed` simulates four months of runs second by second
(warm-up, hills, fatigue, traffic-light stops, noise) with songs whose true
effects are known, and whose effects grow later in a run. Interval sessions
and run-walks have parts, with heart rate that lags the effort; half of them
carry the watch's laps and the rest leave the laps to be found. The real
pipeline then has to make sense of it all: `tests/test_demo.py` checks that
sessions get their laps and kinds both ways, that the known boosters and
draggers come out on top overall and the boosters on hard efforts too, and the
demo's insights show the late-run pattern.
