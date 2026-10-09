# Development guide

## Tooling: uv

The project is managed with [uv](https://docs.astral.sh/uv/). There is no
`requirements.txt`. Dependencies are declared in `pyproject.toml`, and exact
versions for every platform are pinned in `uv.lock`. **Commit both files.**

| File | Purpose |
|---|---|
| `pyproject.toml` | Project metadata, `requires-python` (>= 3.13) and direct dependencies |
| `uv.lock` | Fully resolved, cross-platform lock of every package (direct and transitive). Never edit by hand |
| `.python-version` | Python version uv uses for `.venv` (3.14). Change with `uv python pin <version>` |
| `.venv/` | Local virtual environment created by `uv sync` (git-ignored) |

### Everyday commands

| Task | Command |
|---|---|
| Install / update `.venv` to match the lock | `uv sync` |
| Install exactly the lock, failing if it is stale (CI) | `uv sync --locked` |
| Run anything inside the environment | `uv run <cmd>`, e.g. `uv run flask --app runnify/app.py run --debug` |
| Add a dependency | `uv add <package>` (updates `pyproject.toml`, `uv.lock` and `.venv`) |
| Add a dev-only tool | `uv add --dev <package>` |
| Remove a dependency | `uv remove <package>` |
| Upgrade one package | `uv lock --upgrade-package <package>` then `uv sync` |
| Upgrade everything | `uv lock --upgrade` then `uv sync` |
| Check the lock matches `pyproject.toml` | `uv lock --check` |
| Show the dependency tree | `uv tree` |

You never need to activate `.venv`, because `uv run` uses it automatically. To
activate it anyway, run `.venv\Scripts\activate` on Windows or
`source .venv/bin/activate` on macOS/Linux.

### Hosting platforms that need `requirements.txt`

Generate one from the lock instead of maintaining it by hand:

```bash
uv export --format requirements-txt --no-dev -o requirements.txt
```

### Corporate networks / TLS inspection

If uv fails with `invalid peer certificate: UnknownIssuer`, your network is
re-signing TLS traffic. Tell uv to trust the operating system's certificate store:

```bash
uv sync --system-certs
# or for the whole shell session (PowerShell: $env:UV_SYSTEM_CERTS = "true")
export UV_SYSTEM_CERTS=true
```

## Local setup checklist

1. `uv sync`
2. `cp .env.example .env` and fill in at least `SECRET_KEY` and `FERNET_KEY`
   (the app will not start without `FERNET_KEY`).
3. Optionally point `DATABASE_URL` at PostgreSQL. Without it, a SQLite file is
   created at `runnify/instance/runnify.db`. Music Insights will not work on SQLite.
4. `uv run flask --app runnify/app.py run --debug` from the repository root.

To reset the local SQLite database, stop the server and delete `runnify/instance/runnify.db`.

## Code layout and conventions

- **Flat imports.** Modules import siblings as top-level names (`from models import db`).
  Always launch from the repo root with `flask --app runnify/app.py` or
  `python runnify/app.py` so that `runnify/` lands on `sys.path`.
- **One blueprint per feature** in `runnify/routes/`. Every blueprint is
  registered in `routes/__init__.py::register_blueprints`.
- **Domain logic lives in `runnify/functions/`** and has no knowledge of
  requests or templates. `history_overlap.py` goes further and takes models and
  helpers as arguments, so it has no app imports.
- **Docstrings** use Google style (`Args:` / `Returns:`) on every module, class
  and function. Short inline comments are lower-case.
- **Timestamps** are naive UTC `datetime`s throughout.

### Adding a page

1. Create `runnify/routes/<feature>.py` with a `Blueprint` and view functions
   (add `@login_required` **below** `@<bp>.route(...)`).
2. Register it in `runnify/routes/__init__.py`.
3. Add the template to `runnify/templates/`, extending `base.html`, and any
   assets to `runnify/static/`.
4. Check the URL appears in `uv run flask --app runnify/app.py routes`, and
   update [routes.md](routes.md).

### Changing the schema

There are no migrations. `db.create_all()` creates missing tables only. For
changes to existing tables, either alter them manually or recreate the
database. Consider adding Flask-Migrate (Alembic) if the schema starts changing often.

## Known issues

These were found while documenting the code and have **not** been fixed yet.

| # | Where | Issue | Effect |
|---|---|---|---|
| 2 | `runnify/functions/garmin_service.py` | `from datetime import datetime, time` shadows the `time` module, so `time.sleep(1)` raises `AttributeError`. The broad `except` swallows it | Every FIT download is treated as failed: the file is never saved and `fit_file_path` holds the activity id. Run analysis and scoring then fail for synced runs |
| 3 | `runnify/routes/get_activities.py` | `@login_required` is placed above `@get_activities.route(...)` | Login is not enforced on `/activity/<id>` (data is still scoped to `current_user`) |
| 4 | `runnify/config.py` vs `routes/spocon.py` | Config defines `HISTORY_BATCH_COMMIT_EVERY`, but the upload reads `HISTORY_BATCH_SIZE` | The config value is ignored (the fallback of 1000 is used) |
| 5 | various | `datetime.utcnow()` (deprecated since Python 3.12) and `Query.get()` (legacy in SQLAlchemy 2.x) | Deprecation warnings only |
| 6 | security | `SECRET_KEY` has a hard-coded fallback; forms have no CSRF protection; friend actions are state-changing `GET` requests | Set a real `SECRET_KEY` in every environment; consider Flask-WTF / CSRF tokens |
