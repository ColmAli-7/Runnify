# Route reference

Generated from `uv run flask --app runnify routes`, with each route's
purpose taken from the source. Routes under "Logged-in users" are decorated
with `@login_required`; anonymous users are redirected to the login page.

## Public

| Method | URL | Endpoint | Purpose |
|---|---|---|---|
| GET | `/` | `main.home` | Landing page, personalised when logged in |
| GET, POST | `/login` | `auth.login` | Log in. Form: `email`, `password` |
| GET, POST | `/register` | `auth.register` | Create an account. Form: `name`, `email`, `password` (strength rules apply) |
| GET, POST | `/forgot` | `auth.forgot_password` | Email a password-reset link. Form: `email` |
| GET, POST | `/reset/<token>` | `auth.reset_password` | Set a new password with a reset token (valid 1 hour). Form: `password` |
| GET | `/static/<path:filename>` | `static` | CSS and JS assets |

## Logged-in users

| Method | URL | Endpoint | Purpose |
|---|---|---|---|
| GET | `/logout` | `auth.logout` | End the session |
| GET | `/dashboard` | `dash.dashboard` | Headline stats and monthly mileage chart |
| GET | `/activities` | `activities.activities` | List runs, newest first. Query: `music_only=true` to show only runs with matched songs |
| GET | `/activity/<int:run_id>` | `activities.activity_detail` | Pace/HR timeline with song segments and per-song scores for one of your runs |
| GET, POST | `/garmin` | `garmin.garmin` | Link Garmin Connect and start the background sync. Form: `email`, `password` |
| GET | `/spotify/login` | `spotify.login_spotify` | Start Spotify OAuth |
| GET | `/spotify/callback` | `spotify.callback` | Spotify OAuth redirect target; stores tokens |
| GET, POST | `/spotify/history/upload` | `spotify.upload_history` | Upload Spotify extended streaming history. Form file: `history_zip` (`.zip`) |
| GET | `/help/spotify-upload-guide` | `help.spotify_upload_guide` | How to request and upload Spotify history |
| GET | `/music-insights` | `music_insights.music_insights_page` | Aggregate song performance. Query: `range` = `Last 7 days`, `Last 30 days` (default), `Last 90 days`, `Year to date`, any other value = all time |
| GET | `/friends` | `friends.friends_page` | Friends leaderboard (total km) and pending requests |
| GET, POST | `/friends/search` | `friends.search_users` | Search users by name. Query: `q` |
| GET | `/friends/send/<int:user_id>` | `friends.send_request` | Send a friend request |
| GET | `/friends/accept/<int:request_id>` | `friends.accept_request` | Accept a request addressed to you |
| GET | `/friends/decline/<int:request_id>` | `friends.decline_request` | Decline a request addressed to you |
| GET, POST | `/manage` | `manage.managing` | Change name (`action=change_name`, `new_name`) or password (`new_password`, `confirm_password`). Always requires current `password` |
| GET, POST | `/playlist` | `playlist.playlists` | Playlist generator form (`type`, `pace`, `length`, `mood`). Work in progress |

## Error handling

| Status | Handler | Behaviour |
|---|---|---|
| 404 | `app.page_not_found` | Renders `templates/404.html` |
| 400 | `abort(400)` in activity/upload views | Missing FIT file, empty FIT file, or non-zip upload |
