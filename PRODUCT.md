# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Runners who record runs on a Garmin watch and listen to Spotify while they run, and who want to know which songs actually make them run better. Runnify is open to public sign-ups.

Typical scenes:

- After a run, on a phone or laptop, reviewing how it went and which tracks helped.
- Before a run, picking or building a playlist for a specific session (easy run, intervals, race).
- Occasionally, setting things up: linking Garmin and requesting, then uploading, the Spotify streaming-history export.

Secondary audience: friends on the platform comparing total distance on a leaderboard.

## Product Purpose

Runnify joins two data sources that never meet on their own: second-by-second running data from Garmin (pace and heart rate from the activity's FIT file) and the runner's Spotify listening history. It works out which song was playing at every moment of every run, and how the runner performed during each one.

Success means a runner connects Garmin, uploads their Spotify history, sees which songs lift their pace and which ones drag it, and turns that into a playlist they take on their next run.

## Positioning

Every play is aligned to the exact seconds of the run. Each song is scored against the runner's own pace in that same run, not against other people or generic BPM charts. Strava and Garmin show the run, and Spotify shows the listening; only Runnify shows the effect of one on the other.

## Operating Context

- Garmin Connect account, linked inside Runnify; activities and their FIT files are synced in the background.
- Spotify extended streaming history: requested manually in Spotify's privacy settings, delivered by email (up to 30 days later) as a zip, then uploaded to Runnify.
- Spotify OAuth: used to save generated playlists to the runner's Spotify account.
- Production hosting: Render (web service) with Render Postgres.

## Capabilities and Constraints

- Features: accounts and authentication, Garmin sync, Spotify history import and matching, per-run analysis (pace and heart-rate timeline with songs overlaid), per-song performance scores, dashboard, music insights, friends and distance leaderboard, playlist creator, account settings.
- The Spotify Web API is currently unavailable for testing; Spotify-dependent features must be built defensively and verified with mocks.
- Track audio features (tempo, energy) are not available, so insights must come from listening and running data only.
- Runnify stores personal health and location-derived data (pace, heart rate, run times) and third-party account credentials. Security and privacy are product requirements, not polish.
- Public sign-ups require a privacy notice that explains what is collected and why.

## Brand Commitments

- Name: "Runnify". It is the only element kept from the previous identity; colours, type, layout and imagery are open for replacement (confirmed 2026-10-09).
- Craft bar: work should stand comparison with Apple, Garmin, Strava and Spotify (the user's stated benchmark).

## Evidence on Hand

- No logo or brand assets exist.
- No user counts, testimonials, ratings, press or partnerships exist. None may be invented.
- No real screenshots or shareable real data are available for marketing. Any demonstration data must be authored as clearly labelled sample data.
- Runnify is not affiliated with Garmin or Spotify; their names may be used only to describe the integrations.

## Product Principles

1. **Your baseline, not the world's.** Every score compares the runner with themselves in the same run.
2. **Show the evidence.** Every finding carries its sample size and confidence; no false precision.
3. **Private by default.** Health and location data is minimised, encrypted where it is sensitive, and deletable by the runner.
4. **Setup is the hard part.** Linking accounts and waiting on Spotify's export is where people drop off, so guide it step by step.
5. **Make it actionable.** Insights lead somewhere: a song to keep, a song to skip, a playlist to build.

## Accessibility & Inclusion

Assumed default for a public product (not separately specified by the user): WCAG 2.2 AA, full keyboard operability, and respect for reduced-motion preferences.
