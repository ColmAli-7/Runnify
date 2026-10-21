# Architecture

Runnify is one server-rendered Flask application. There is no separate
frontend build: pages are Jinja templates, styles are plain CSS, and a few
small JavaScript modules add behaviour on top of pages that already work
without them. Every asset, font and script is served by the app itself.

## Components

```mermaid
flowchart LR
    Browser -->|HTTPS| Flask["Flask app<br/>runnify.create_app()"]
    Flask --> Routes["routes/*<br/>one blueprint per area"]
    Routes --> Services["services/*<br/>domain logic"]
    Routes --> Security["security/*"]
    Services --> Models["models.py<br/>SQLAlchemy"]
    Models --> DB[("SQLite or PostgreSQL")]
    Services -->|garminconnect, background thread| Garmin["Garmin Connect"]
    Services -->|spotipy| Spotify["Spotify Web API<br/>(saving playlists only)"]
    Services -->|Flask-Mail| Mail["SMTP server"]
```

| Layer | Location | Responsibility |
|---|---|---|
| App factory | `runnify/__init__.py` | `create_app()` loads a config profile, validates production settings, binds the extensions, registers blueprints, filters, CLI commands and the error pages |
| Config | `runnify/config.py` | Settings profiles (`development`, `production`, `test`) read from environment variables |
| Extensions | `runnify/extensions.py` | Shared `db`, `migrate`, `csrf`, `limiter`, `mail` and `login_manager`; SQLite connections are tuned here (WAL, busy timeout, foreign keys) |
| Models | `runnify/models.py` | Every table, the user loader and the session-token check |
| Security | `runnify/security/` | Password hashing and policy, lockout, reset tokens, encryption at rest, two-step verification, security headers, rate-limit keys, safe redirects, the audit log |
| Domain logic | `runnify/services/` | Garmin sync, FIT parsing, run streams, laps and kinds of run, typed workouts, history import, scoring, analysis, insights, each song's record, results, dashboard, playlists, charts, account export and deletion. No request handling |
| Routes | `runnify/routes/` | Request handling and rendering, one blueprint per area |
| Content | `runnify/content/` | The landing page's sample results, computed by the real engine from simulated runs |
| Templates | `runnify/templates/` | `layouts/` (base, public, app, auth, settings), `macros/` (fields, results tables, charts), then one folder per area |
| Static | `runnify/static/` | `css/ui/` (the design system), `css/pages/`, `js/`, the Geist font, icons and vendored GSAP |

## Data model

```mermaid
erDiagram
    users ||--o{ runs : "has"
    runs ||--o| run_streams : "recorded as"
    runs ||--o{ run_laps : "split into"
    users ||--o{ user_song_history : "listened"
    songs ||--o{ user_song_history : "played as"
    runs ||--o{ user_song_history : "during"
    user_song_history ||--o{ run_song_analysis : "measured as"
    users ||--o{ playlists : "built"
    playlists ||--o{ playlist_tracks : "contains"
    users ||--o{ recovery_codes : "holds"
    users ||--o{ security_events : "logged"
    users ||--o{ friends : "both ways"
    users ||--o{ friend_requests : "sender / receiver"
```

| Table | Holds |
|---|---|
| `users` | Name, email, Argon2id password hash, encrypted Garmin and Spotify tokens, sync and import status with the progress of a running one, consent timestamps and policy version, lockout counters, the session token, the encrypted two-step secret |
| `runs` | One Garmin run: start (UTC) and the runner's UTC offset at the time, distance in metres, duration in seconds, average heart rate and pace, its kind of run (and whether the runner chose it), where its laps came from, and a typed workout as Runnify read it |
| `run_streams` | The run's samples, one a second (offsets, pace to 0.1 s/km, heart rate, and cadence and distance when recorded), and the watch's own laps; zlib-compressed JSON, about 15 KB for an hour |
| `run_laps` | The run's laps in order: start and end second, kind (warm-up, hard, steady, jog, walk or cool-down), distance, moving time and average heart rate |
| `songs` | Spotify track id, name, artist and a learned track length; only songs that played during someone's run, and those no play or playlist uses are removed |
| `user_song_history` | A play that overlapped a run: when it started, seconds played, whether it was skipped |
| `run_song_analysis` | A play's measured effect: `pace_delta` (s/km, the lift after any charge for extra effort), `hr_delta`, seconds measured, position in the run, the kind of lap it was measured on, the effort charge, method version |
| `playlists`, `playlist_tracks` | Saved playlists, each track with the lift and plays it was chosen on |
| `recovery_codes` | SHA-256 hashes of unused two-step recovery codes |
| `security_events` | Sign-ins and account changes with a truncated IP prefix and a short user agent; kept 90 days |
| `friends`, `friend_requests` | Friendships (stored in both directions) and pending requests |

All timestamps are naive UTC; pages show a run's start on its own clock (`Run.local_start`). Alembic revisions in `migrations/versions/` create
and evolve the schema; a test fails if the models and migrations ever drift apart.

## Pipeline 1: Garmin sync

1. **Linking** (`POST /connections/garmin`). The Garmin password is used once to
   sign in through `garminconnect`. If Garmin asks for a two-step code, the
   half-finished sign-in waits in memory for five minutes. Runnify stores the
   resulting session tokens, encrypted with Fernet, and never the password.
2. **Syncing** runs on a background thread with its own app context
   (`services/garmin.start_background_sync`). It lists the activities 100 at a
   time (a later sync only back to a fortnight before the last full one, so a
   run the watch uploads late is still found), skips anything that isn't a run
   or is already stored, and downloads the rest three at a time on worker
   threads (`_Garmin.downloads`) while the job's own thread stores each run as
   it arrives, newest first: its FIT file read in memory, its stream, and its
   laps and kind (`services/laps.refresh_laps`), judged against the runner's
   usual pace over all of their runs, new ones included. Each run is committed
   on its own. Afterwards every run's kind is worked out again and refreshed
   tokens are saved. The outcome is recorded on the user (`garmin_sync_state`,
   `garmin_sync_message`; see [Background jobs](#background-jobs)).
   - **A stalling Garmin.** Every call (sign-in, listing, each download) may
     take 90 seconds at most, and the job keeps reporting while it waits. A
     download that stalls or fails is left for the next sync rather than
     stored without its samples; a run Garmin has no file for is kept without
     one. Five failures in a row stop the sync for now.
   - **Slowing down.** When Garmin answers "too many requests" (429), the
     downloads pause for a minute, then two, then four, and carry on one at a
     time; a fourth refusal stops the sync for now. The rest come in on the
     next sync, and the last full sync time only moves on once nothing is
     left.
3. **Parsing** (`services/fit.py`). Runnify reads the `record` and `lap`
   messages itself, with one precompiled `struct` per message definition that
   reads the fields it uses and steps over the rest, giving exactly
   fitparse's values about thirty times quicker. Anything unusual (old
   devices' compressed speed and distance, arrays, times relative to
   power-on, a broken file) goes to fitparse. Pace comes from the recorded
   speed, or the change in distance when speed is missing. Samples slower
   than 15:00/km count as stopped and samples faster than 2:00/km as GPS
   glitches; both carry no pace. The rest is lightly smoothed, and the whole
   series is spread to one sample a second (smart recording and auto-pause
   leave gaps). Cadence, distance and the watch's laps are kept. FIT files
   are never kept on disk; `flask --app runnify laps refetch` downloads old
   runs again for the laps and cadence they were stored without.

## Pipeline 2: Spotify history import

1. **Upload** (`POST /import`). The page's script sends the zip with a progress
   bar (the form also works without it). The zip is saved to a temporary file
   and checked before anything is read: entry count, total uncompressed size
   and compression ratio are capped, so a zip bomb is refused.
2. **Import** runs on a background thread (`services/imports.run_import`). Every
   JSON file is streamed with `ijson`, so large histories never sit in memory.
   Podcasts and videos are ignored. Each play's interval is
   `[ts - ms_played, ts)`, because Spotify's `ts` is when playback stopped. The
   play is intersected with the runs it overlaps, found by bisecting the runs'
   start times; each overlap becomes a `user_song_history` row unless the
   runner already has it (checked in memory), so a newer upload only adds
   what's new. Everything is read and matched before anything is written, then
   written in batches, so the database is never held while the file is read.
   Only songs that played during a run join `songs`; complete plays, during a
   run or not, teach a song its length.
3. **Scoring.** Every run that gained plays is re-scored, a run at a time and
   committed as it goes (`services/analysis.rescore_run`): its laps are worked
   out again first, unless the runner set them, and each song is measured
   against the same kind of lap, the run prepared once for all of its songs
   (`services/scoring.RunScorer`). Every run's kind is then worked out again,
   and the uploaded file is deleted whatever the outcome. See
   [scoring.md](scoring.md).

## Background jobs

A Garmin sync and a history import each run on a thread inside the web process
(`services/jobs.py`). While one runs it writes what it is doing, how far it has
got and when, on the user, about once a second (`Progress.report`, which also
commits; jobs report only between whole runs). Pages read the job from there
(`jobs.job`); `GET /jobs` serves both as JSON, and `js/jobs.js` polls it every
two seconds while one runs, moving the message and bar on. Import and
Connections show the job in full and reload when it ends (unless the runner is
typing into a form there); every other signed-in page shows a notice that says
how it ended. A deploy or restart ends a job without a word: one that hasn't
reported for ten minutes counts as interrupted, the pages say so, and the
runner can start it again.

## Changing a run's laps

The run page's laps card opens to small forms (the kind of run, each lap's
kind, joining and splitting laps, a typed workout), each working without
scripts. They all post to `/runs/<id>/laps` (`routes/runs.laps`), which looks
the run up through the signed-in runner, makes the change
(`services/laps.py`, `services/workouts.py`), re-scores the run and goes back
to the run page; a GET of the same address goes back too, so a form that
expired lands on the run.

## Spotify connection

Only used to save playlists. `/spotify/login` sends the user to Spotify with a
random `state` kept in the session; `/spotify/callback` checks it, exchanges the
code and stores the tokens encrypted. Each request uses an in-memory token
cache, so tokens never mix between users. Playlists are created private and
filled 100 tracks per request.

## Frontend

- **Layouts.** `layouts/base.html` is the document; `public.html` (marketing,
  legal, sign-in) and `app.html` (signed-in pages with the main navigation, a
  tab bar on phones) extend it; `auth.html` and `settings.html` add their page
  structures.
- **Design system.** `static/css/ui/` holds the tokens (colour, type scale,
  spacing, motion), the reset and base styles, the layout primitives and the
  components, in cascade layers (`reset, base, layout, components, pages,
  utilities`). Each page adds its own stylesheet from `static/css/pages/`. See
  [DESIGN.md](../DESIGN.md), and [docs/redesign/](redesign/plan.md) for how the
  current design came about.
- **Themes.** Every colour token holds a light and a dark value with
  `light-dark()`. The theme follows the system unless the runner picks Light or
  Dark (kept in `localStorage` as `runnify-theme`); `js/theme.js` runs in
  `<head>` to apply that choice before the page paints.
- **Charts** are inline SVG drawn from geometry computed on the server
  (`services/charts.py`): the line and its filled area, a moving-average line,
  a band per song, a lane of song blocks and a lane of lap blocks, and on each
  song's page a dot per play with a trend line. Positions are percentages and
  lines are drawn in a stretched box, so a chart takes its size from CSS and
  keeps crisp text and strokes at any width, with no inline styles.
  `js/pages/run.js` adds scrubbing with the pointer, a finger or the arrow keys.
- **Scripts** are ES modules attached through `data-*` attributes; data for a
  script travels in a `<script type="application/json">` block. `js/app.js`
  runs on every page (menus, dismissible notices, password reveal,
  confirmations, copy and print buttons, linked table rows), and `js/jobs.js`
  on every signed-in page keeps a running sync's or import's progress moving;
  page modules live in `js/pages/`. Without JavaScript every page still works.
- **Motion.** Only the landing page tells a moving story, with the vendored
  GSAP and its ScrollTrigger plugin: the headline's words rise, a sample run
  replays with its songs, the four "how a song gets its score" steps draw
  themselves as they are reached, and the closing panel draws the run's pace
  line. Nothing fades in on scroll. The app moves only in response to the
  runner (presses, menus, the run chart's scrubbing). Nothing moves when the
  visitor prefers reduced motion, and without scripts every chart is drawn
  complete.

## Security

The measures are summarised in [SECURITY.md](../SECURITY.md). In short:
Argon2id passwords with a NIST-style policy, lockout and rate limits, CSRF
tokens on every form, sessions that end on every device when the password
changes, single-use reset links, optional two-step verification, encrypted
third-party tokens, a strict Content-Security-Policy and other headers on every
response, and an activity log users can read.
