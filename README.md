# Runnify

Analyse how music impacts your running performance.

Runnify is a Flask web application that combines **Garmin** running activities
with your **Spotify** extended streaming history. It works out which songs were
playing during each run and scores how fast you ran during each song compared
with the rest of that run, so you can see which tracks actually push your pace.

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [Using Runnify](#using-runnify)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Limitations](#limitations)
- [Author](#author)

## Features

- **Garmin integration**: link your Garmin Connect account and every running
  activity, including its `.fit` file, is imported in the background
- **Spotify history matching**: upload your extended streaming history and plays
  are matched to runs by timestamp overlap
- **Per-song performance score**: a 0–100 score for every song played during a
  run, where 50 is your average pace for that run (see [docs/scoring.md](docs/scoring.md))
- **Run analysis**: pace and heart-rate charts with song segments overlaid
- **Dashboard and Music Insights**: headline stats, monthly mileage, best and
  most-played songs, score trends
- **Friends and leaderboard**: send friend requests and compare total distance
- **Account management**: password reset by email, and name and password changes

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13+, Flask, Flask-Login, Flask-Mail |
| Database | PostgreSQL (SQLite fallback for local dev) via SQLAlchemy / Flask-SQLAlchemy |
| Integrations | `garminconnect`, `spotipy`, `fitparse`, `ijson` |
| Security | Werkzeug password hashing, `itsdangerous` reset tokens, Fernet-encrypted Garmin passwords |
| Frontend | Jinja2 templates, CSS, vanilla JavaScript, Chart.js, Bootstrap, Font Awesome |
| Tooling | [uv](https://docs.astral.sh/uv/) for Python, dependency and lock-file management |

## Quick start

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/),
plus a PostgreSQL database if you want the Music Insights page. uv installs the
pinned Python version for you if it is missing.

```bash
git clone https://github.com/ColmAli-7/Runnify.git
cd Runnify

# create .venv and install the exact locked dependency versions
uv sync

# create your local config, then fill in the values (see below)
cp .env.example .env

# run the development server
uv run flask --app runnify/app.py run --debug
```

Open <http://127.0.0.1:5000>. Database tables are created automatically on first start.

> **Behind a corporate proxy?** If `uv sync` fails with `invalid peer certificate: UnknownIssuer`,
> run it with `--system-certs` (or set `UV_SYSTEM_CERTS=true`) so uv trusts your OS certificate store.

## Configuration

All settings are read from environment variables, loaded from a `.env` file in
the project root. [`.env.example`](.env.example) lists every variable with comments.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SECRET_KEY` | **Yes** in production | `runnify-secret-key` | Signs session cookies and password-reset tokens |
| `DATABASE_URL` | Recommended | `sqlite:///runnify.db` (in `runnify/instance/`) | SQLAlchemy database URL. Use PostgreSQL in production |
| `FERNET_KEY` | **Yes** | none | Encrypts stored Garmin passwords. **The app will not start without it** |
| `SPOTIFY_CLIENT_ID` | For Spotify login | none | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | For Spotify login | none | Spotify app client secret |
| `SPOTIFY_REDIRECT_URI` | For Spotify login | none | Must exactly match the redirect URI registered in the Spotify dashboard, e.g. `http://127.0.0.1:5000/spotify/callback` |
| `SPOTIFY_SCOPE` | For Spotify login | none | Space-separated OAuth scopes |
| `MAIL_SERVER` | For password reset | `smtp.gmail.com` | SMTP host |
| `MAIL_PORT` | For password reset | `587` | SMTP port |
| `MAIL_USE_TLS` | For password reset | `True` | Use STARTTLS |
| `MAIL_USE_SSL` | For password reset | `False` | Use implicit SSL |
| `MAIL_USERNAME` | For password reset | none | SMTP username |
| `MAIL_PASSWORD` | For password reset | none | SMTP password / app password |
| `MAIL_DEFAULT_SENDER` | For password reset | `runnify.dev@gmail.com` | From address on reset emails |

Generate the secrets with:

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"                                # SECRET_KEY
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" # FERNET_KEY
```

Other tunables, such as maximum upload size (600 MB) and the minimum song/run
overlap, live in [`runnify/config.py`](runnify/config.py).

## Running the app

Always run commands from the **repository root**:

```bash
# development server with auto-reload and debugger
uv run flask --app runnify/app.py run --debug

# list every URL the app serves
uv run flask --app runnify/app.py routes

# or run the module directly (debug off)
uv run python runnify/app.py
```

Downloaded Garmin `.fit` files are written to `fit_files/` in the current
working directory. That folder holds personal GPS and heart-rate data and is git-ignored.

## Using Runnify

1. **Register** and log in.
2. **Connect Garmin** (`/garmin`). Your credentials are verified, the password
   is stored encrypted, and your running activities are imported in a background
   thread. Garmin may rate-limit large first syncs.
3. **Request your Spotify data.** In Spotify's privacy settings, request
   **Extended streaming history**. It can take up to 30 days to arrive.
   The in-app guide at `/help/spotify-upload-guide` walks you through it.
4. **Upload the zip** (`/spotify/history/upload`). Plays that overlap a run are
   saved and each one is scored.
5. **Explore** the dashboard, each run's analysis page (`/activities`), Music
   Insights and the friends leaderboard.

## Project structure

```text
Runnify/
├── pyproject.toml          # project metadata and dependencies (managed by uv)
├── uv.lock                 # exact, cross-platform locked versions; commit this
├── .python-version         # Python version uv uses for .venv
├── .env.example            # template for your local .env
├── docs/                   # in-depth documentation (see below)
└── runnify/                # application source (flat imports, not a package)
    ├── app.py              # entry point: creates the app, extensions, tables, blueprints
    ├── config.py           # Config class populated from environment variables
    ├── models.py           # SQLAlchemy models
    ├── functions/          # domain logic, no HTTP
    │   ├── fit_util.py         # parse .fit files into time/HR/pace series
    │   ├── garmin_service.py   # sync running activities from Garmin Connect
    │   ├── history_overlap.py  # import Spotify history zip and match plays to runs
    │   ├── song_segments.py    # songs that were playing during a given run
    │   └── validation.py       # password strength rules
    ├── routes/             # one Flask blueprint per feature area
    │   ├── auth.py  dash.py  friends.py  garcon.py  get_activities.py
    │   ├── help.py  main.py  manage.py  music_insights.py  playlist.py  spocon.py
    ├── templates/          # Jinja2 pages
    └── static/             # css/ and js/
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Components, data model (ER diagram), Garmin sync and Spotify import pipelines |
| [docs/routes.md](docs/routes.md) | Every URL, its method, auth requirement and purpose |
| [docs/scoring.md](docs/scoring.md) | How songs are matched to runs and how the performance score is calculated |
| [docs/development.md](docs/development.md) | uv workflow, managing dependencies, conventions and troubleshooting |

All Python modules, classes and functions also have docstrings.

## Limitations

- **No migrations.** Tables are created with `db.create_all()` on start-up.
  Schema changes to existing tables must be applied manually.
- **Playlist generator is a work in progress.** The form is captured but no playlist is built yet.
- **Garmin rate limits.** Requests may be throttled if made too frequently.
- **Spotify history is manual.** Extended streaming history has to be requested
  from Spotify's account privacy settings and uploaded as a zip.

## Author

Colm Ali
