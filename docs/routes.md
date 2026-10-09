# Route reference

Every URL Runnify serves (`uv run flask --app runnify routes` prints the same
table). Pages under "Signed in" need an account; anonymous visitors are sent
to the sign-in page and back afterwards. Every `POST` needs a CSRF token, and
signed-in users who haven't agreed to the current policies are asked to first
(see [Consent](#consent)).

## Public

| Method | URL | Endpoint | Purpose |
|---|---|---|---|
| GET | `/` | `main.home` | Landing page (signed-in users go to the dashboard) |
| GET, POST | `/login` | `auth.login` | Sign in. Form: `email`, `password`, `remember` |
| GET, POST | `/login/verify` | `auth.verify_two_factor` | Second sign-in step when two-step verification is on. Form: `code` (authenticator or recovery code) |
| GET, POST | `/register` | `auth.register` | Create an account. Form: `name`, `email`, `password`, `accept_terms`, `data_consent` |
| GET, POST | `/forgot` | `auth.forgot_password` | Email a single-use reset link; same answer whether or not the account exists. Form: `email` |
| GET | `/reset/<token>` | `auth.reset_password` | The emailed link: checks the token, moves it into the session and redirects to `/reset` |
| GET, POST | `/reset` | `auth.choose_new_password` | Choose a new password. Form: `password`, `confirm` |
| GET | `/privacy`, `/terms`, `/cookies` | `legal.*` | Privacy policy, terms of use, cookie policy |
| GET | `/static/<path>` | `static` | CSS, JavaScript, fonts and images |

## Signed in

| Method | URL | Endpoint | Purpose |
|---|---|---|---|
| POST | `/logout` | `auth.logout` | Sign out |
| GET | `/dashboard` | `dashboard.index` | Set-up progress, totals, latest run, top songs and weekly distance |
| GET | `/runs` | `runs.index` | Every run, newest first. Query: `music_only=true` |
| GET | `/runs/<id>` | `runs.detail` | One run: pace and heart rate with the songs played, and each song's effect |
| GET | `/insights` | `insights.index` | Findings across runs. Query: `range` = `30d`, `90d` (default), `year` or `all` |
| GET, POST | `/playlists` | `playlists.index` | Saved playlists, and the builder. Form: `session`, `minutes`, `include_untested` |
| GET | `/playlists/<id>` | `playlists.detail` | A playlist's tracks and the evidence behind each |
| POST | `/playlists/<id>/spotify` | `playlists.send_to_spotify` | Save the playlist to Spotify as a private playlist |
| POST | `/playlists/<id>/delete` | `playlists.delete` | Delete the playlist from Runnify |
| GET | `/friends` | `friends.index` | Distance leaderboard and friend requests |
| GET, POST | `/friends/search` | `friends.search` | Find people by name. Query: `q` |
| POST | `/friends/<user_id>/request` | `friends.send_request` | Send a friend request |
| POST | `/friends/requests/<id>/accept` | `friends.accept` | Accept a request sent to you |
| POST | `/friends/requests/<id>/decline` | `friends.decline` | Decline a request sent to you |
| GET | `/connections` | `connections.index` | Garmin and Spotify status |
| POST | `/connections/garmin` | `connections.link_garmin` | Sign in to Garmin once to link it (the password is never stored). Form: `email`, `password` |
| POST | `/connections/garmin/verify` | `connections.verify_garmin` | Garmin's two-step verification code. Form: `code` |
| POST | `/connections/garmin/sync` | `connections.sync_garmin` | Fetch new runs now |
| POST | `/connections/garmin/disconnect` | `connections.disconnect_garmin` | Unlink Garmin (imported runs are kept) |
| POST | `/connections/spotify/disconnect` | `connections.disconnect_spotify` | Forget the Spotify connection |
| GET | `/spotify/login` | `spotify.login_spotify` | Start Spotify sign-in (with an anti-CSRF `state`) |
| GET | `/spotify/callback` | `spotify.callback` | Spotify's redirect target; must match `SPOTIFY_REDIRECT_URI` |
| GET, POST | `/import` | `imports.index` | How to get the Spotify export, and the upload. Form file: `history_zip` |
| GET, POST | `/settings` | `settings.index` | Name, password, sessions, your data and security activity |
| GET, POST | `/settings/two-factor` | `settings.two_factor` | Set up or manage two-step verification |
| POST | `/settings/two-factor/disable` | `settings.disable_two_factor` | Turn it off (password plus a code) |
| POST | `/settings/two-factor/recovery-codes` | `settings.new_recovery_codes` | Replace the recovery codes (password) |
| POST | `/settings/export` | `settings.export_data` | Download your data as JSON (password) |
| POST | `/settings/delete` | `settings.delete_account` | Delete your account and all of its data (password and confirmation) |

## Consent

| Method | URL | Endpoint | Purpose |
|---|---|---|---|
| GET, POST | `/consent` | `legal.consent` | Agree to the current terms and data processing. While consent is missing, only the policies, sign-out, settings (download or delete your data) and this page are reachable |

## Errors

| Status | When |
|---|---|
| 400 | Malformed requests, such as a Spotify callback without a code |
| 404 | Unknown pages, and anything belonging to another user |
| 429 | A rate limit was reached |
| CSRF failure | The form is shown again with a "form expired" message |
