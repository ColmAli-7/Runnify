# Runnify

Find the songs that make you run faster.

Runnify lines up your Spotify listening history with the second-by-second pace
from your Garmin runs, then ranks every song by how much faster or slower you
ran while it played. Each song is measured against your own running in the
minutes around it, in the same run, so warm-ups, hills and tired legs mostly
cancel out.

## Contents

- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Everyday commands](#everyday-commands)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Known limitations](#known-limitations)

## What it does

- **Garmin sync.** Link Garmin Connect once; Runnify keeps an encrypted session
  token (never the password) and imports each run with its second-by-second
  pace and heart rate, in the background.
- **Spotify history matching.** Upload the extended streaming history zip
  Spotify emails you. Only plays that overlap a run are kept; the file is
  deleted as soon as it has been read.
- **A results sheet for every run.** Pace and heart rate through the run with a
  band for each song, and every song ranked by its lift in s/km.
- **Insights.** Power songs and drag songs (ranked on shrunk effects, so one
  lucky play can't top the chart), where in a run songs work hardest, top
  artists, heart raisers and the most skipped songs, over a chosen range.
- **Playlists for a session.** Easy, tempo, long, race or intervals, built from
  the songs that have actually lifted your pace and ordered to suit the
  session; save them to Spotify as private playlists.
- **Friends.** A monthly distance leaderboard, friend requests and search.
- **Account security.** Argon2id passwords, optional two-step verification
  with recovery codes, lockout after repeated failures, a security activity
  log, signing out other devices, and downloading or deleting all of your data.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13+, Flask, Flask-Login, Flask-WTF, Flask-Limiter, Flask-Mail |
| Data | SQLAlchemy 2 with Flask-SQLAlchemy, Alembic through Flask-Migrate. SQLite by default, PostgreSQL supported |
| Integrations | `garminconnect`, `fitparse`, `spotipy`, `ijson` |
| Security | Argon2id (`argon2-cffi`), Fernet encryption at rest (`cryptography`), TOTP (`pyotp`), QR codes (`segno`), a strict Content-Security-Policy |
| Frontend | Server-rendered Jinja templates, plain CSS with cascade layers, plain JavaScript modules, inline SVG charts drawn on the server, GSAP for the landing page motion, the Geist typeface. Everything is self-hosted |
| Tooling | [uv](https://docs.astral.sh/uv/), pytest, ruff |

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). It installs the
right Python for you, and the database is a local SQLite file by default.

```bash
git clone https://github.com/ColmAli-7/Runnify.git
cd Runnify
uv sync                                      # install the locked dependencies into .venv
cp .env.example .env                         # then set FERNET_KEY (see below)
uv run flask --app runnify db upgrade        # create the database
uv run flask --app runnify run --debug       # http://127.0.0.1:5000
```

To explore with realistic data, seed the demo account (four months of simulated
runs with songs, friends and a playlist; development only):

```bash
uv run flask --app runnify demo seed
```

Then sign in as `demo@runnify.test` with the password you chose.

> **Behind a TLS-inspecting proxy?** If `uv sync` fails with `invalid peer certificate`,
> run it with `--system-certs` (or set `UV_SYSTEM_CERTS=true`) so uv trusts the OS certificate store.

## Configuration

Settings come from environment variables, loaded from `.env` in the project root.
[`.env.example`](.env.example) lists every variable with comments. The ones you are
most likely to need:

| Variable | Required | Purpose |
|---|---|---|
| `APP_ENV` | No (`development`) | `production` turns on secure cookies, HSTS and a start-up check of every setting below |
| `SECRET_KEY` | In production | Signs sessions and tokens; 32+ random characters |
| `FERNET_KEY` | To link Garmin or Spotify | Encrypts stored third-party tokens; `FERNET_KEYS` rotates keys without downtime |
| `DATABASE_URL` | No | SQLite at `runnify/instance/runnify.db` by default; `postgres://` URLs work too |
| `PUBLIC_BASE_URL` | In production | The public `https://` origin used in emailed links |
| `ALLOWED_HOSTS` | In production | Host names the site answers on; anything else gets a 400 |
| `RATELIMIT_STORAGE_URI` | Recommended in production | Shared store (such as Redis) so rate limits hold across workers |
| `OPERATOR_NAME`, `CONTACT_EMAIL` | Recommended | Who runs the site and how to reach them, shown in the privacy policy and footer |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`, `SPOTIFY_SCOPE` | To save playlists to Spotify | Spotify app credentials |
| `MAIL_SERVER` and the other `MAIL_*` | For real email | Without `MAIL_SERVER`, emails are written to the log |

Generate the secrets with:

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"                                 # SECRET_KEY
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
```

## Everyday commands

| Task | Command |
|---|---|
| Run the tests | `uv run pytest` |
| Lint and format | `uv run ruff check .` and `uv run ruff format .` |
| Check colour contrast | `uv run python scripts/check_contrast.py` |
| List every URL | `uv run flask --app runnify routes` |
| Re-score every run after the method changes | `uv run flask --app runnify scores rebuild` |
| Move old FIT files into the database | `uv run flask --app runnify streams backfill` |

## Project structure

```text
Runnify/
├── pyproject.toml, uv.lock     project metadata and the exact locked dependencies
├── .env.example                every setting, documented
├── PRODUCT.md, DESIGN.md       who the product is for, and the design system
├── SECURITY.md                 how accounts and data are protected, and how to report a problem
├── docs/                       architecture, scoring, routes, development, deployment
├── migrations/                 Alembic revisions
├── scripts/                    icon builder and contrast checker
├── tests/                      pytest suite
└── runnify/
    ├── __init__.py             create_app(), the application factory
    ├── config.py               settings profiles read from the environment
    ├── extensions.py           shared extension instances
    ├── models.py               SQLAlchemy models
    ├── filters.py              how numbers are shown (pace, lift, time, distance)
    ├── cli.py                  flask commands (demo, scores, streams)
    ├── content/                the landing page's sample results, computed by the real engine
    ├── security/               passwords, lockout, tokens, encryption, two-step, headers, audit log
    ├── services/               domain logic: Garmin, FIT, streams, scoring, analysis, insights,
    │                           results, dashboard, playlists, charts, imports, account
    ├── routes/                 one blueprint per area
    ├── templates/              layouts/, macros/ and one folder per area
    └── static/                 css/ui (design system), css/pages, js, fonts, img, vendor
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Components, data model, the Garmin and Spotify pipelines, the frontend |
| [docs/scoring.md](docs/scoring.md) | How plays are matched to runs, how a song's effect is measured, and how insights and playlists use it |
| [docs/routes.md](docs/routes.md) | Every URL, its method, who can use it and what it does |
| [docs/development.md](docs/development.md) | Local workflow, conventions, tests, migrations and the demo data |
| [docs/deployment.md](docs/deployment.md) | Running Runnify on Render |
| [DESIGN.md](DESIGN.md) | The visual system: tokens, components and rules |
| [SECURITY.md](SECURITY.md) | Security measures and how to report a vulnerability |

Every module, class and function also has a docstring.

## Known limitations

- **Spotify history is manual.** Spotify only provides the extended streaming
  history on request, by email, which can take up to 30 days.
- **Spotify's Web API is needed only to save playlists**, and that path is
  covered by tests with a stubbed client rather than live calls.
- **Run times follow the watch.** Each run is shown on the clock it was
  recorded in, from Garmin's local start time; runs imported before that was
  stored show UTC until Garmin is next synced.
- **Garmin rate limits.** Large first syncs may be throttled by Garmin.

## Author

Colm Ali
