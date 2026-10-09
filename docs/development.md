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
| Run anything inside the environment | `uv run <cmd>`, e.g. `uv run flask --app runnify run --debug` |
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
   created at `runnify/instance/runnify.db`.
4. `uv run flask --app runnify db upgrade` to create the database tables.
5. `uv run flask --app runnify run --debug` from the repository root.

To reset the local SQLite database, stop the server and delete `runnify/instance/runnify.db`.

## Code layout and conventions

- **Package imports.** Modules import each other absolutely (`from runnify.models import User`);
  shared extension instances live in `runnify/extensions.py`.
- **One blueprint per feature** in `runnify/routes/`. Every blueprint is
  registered in `routes/__init__.py::register_blueprints`.
- **Domain logic lives in `runnify/services/`** and has no knowledge of
  requests or templates. `history_import.py` goes further and takes models and
  helpers as arguments, so it has no app imports.
- **Docstrings** use Google style (`Args:` / `Returns:`) on every module, class
  and function. Short inline comments are lower-case.
- **Timestamps** are naive UTC `datetime`s throughout.

### Adding a page

1. Create `runnify/routes/<feature>.py` with a `bp = Blueprint(...)` and view functions
   (add `@login_required` **below** `@<bp>.route(...)`).
2. Register it in `runnify/routes/__init__.py`.
3. Add the template to `runnify/templates/`, extending `base.html`, and any
   assets to `runnify/static/`.
4. Check the URL appears in `uv run flask --app runnify routes`, and
   update [routes.md](routes.md).

### Changing the schema

The schema is managed with Alembic through Flask-Migrate; revisions live in
`migrations/versions/`. After changing a model:

```bash
uv run flask --app runnify db migrate -m "describe the change"   # autogenerate a revision
# review the generated file, then apply it
uv run flask --app runnify db upgrade
```

`tests/test_migrations.py` fails if the models and migrations ever drift apart.

A database created before migrations existed (by the old `db.create_all()`)
already has the baseline tables. Mark it as being at the baseline once, then
upgrade as normal:

```bash
uv run flask --app runnify db stamp 0001
uv run flask --app runnify db upgrade
```
