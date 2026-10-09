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
3. The database is a SQLite file at `runnify/instance/runnify.db` by default
   (the setup used for testing for now). To use PostgreSQL instead, set
   `DATABASE_URL`; connections are tuned for SQLite automatically (WAL mode,
   a busy timeout and enforced foreign keys).
4. `uv run flask --app runnify db upgrade` to create the database tables.
5. `uv run flask --app runnify run --debug` from the repository root.

To reset the local SQLite database, stop the server and delete `runnify/instance/runnify.db`.

## Code layout and conventions

- **Package imports.** Modules import each other absolutely (`from runnify.models import User`);
  shared extension instances live in `runnify/extensions.py`.
- **One blueprint per area** in `runnify/routes/`, registered in
  `routes/__init__.py::register_blueprints`. Routes stay thin: they read the
  request, call services and render.
- **Domain logic lives in `runnify/services/`** and knows nothing about
  requests or templates, so it can be tested directly.
- **Numbers are formatted in one place**, the Jinja filters in
  `runnify/filters.py` (`pace`, `run_pace`, `duration`, `km`, `lift`,
  `lift_number`, `day`, `ago` and so on). Effects always read "+9 s/km" with a
  true minus sign for negatives.
- **Docstrings** use Google style (`Args:` / `Returns:`) on every module, class
  and function. Comments are short and lower-case, and say why rather than what.
- **Timestamps** are naive UTC `datetime`s throughout.
- **Copy** is plain and specific, in sentence case, with no em dashes.

### Frontend rules

- Pages extend a layout: `layouts/public.html` for signed-out pages,
  `layouts/app.html` for signed-in ones (`layouts/auth.html` and
  `layouts/settings.html` build on those).
- Use the macros in `templates/macros/`: `field` and `check` for form fields
  (labels, hints, inline errors and `aria-describedby` are wired for you),
  `results_table` and `effect_list` for ranked songs, `run_chart`,
  `bar_chart` and `meter` for charts, `lift` for an effect badge.
- **No inline code.** No `style="..."`, no inline `<script>`, no `on*=`
  handlers: the Content-Security-Policy blocks them and
  `tests/test_security_headers.py` fails if a template uses one. Pass data to a
  script with the `data_island` macro and attach behaviour in a module under
  `static/js/` through `data-*` attributes. Scripts may set styles through
  `element.style`, which the policy allows.
- Styles go in the right cascade layer: shared pieces in `static/css/ui/`,
  page-only styles in `static/css/pages/<page>.css`, loaded from the page's
  `styles` block. Use the tokens in `tokens.css`; never hard-code a colour.
- Every page works without JavaScript, and nothing moves when the visitor
  prefers reduced motion.
- After changing colours, run `uv run python scripts/check_contrast.py`.

### Adding a page

1. Add a view to the area's blueprint in `runnify/routes/` (put
   `@login_required` below `@bp.route(...)`), or create a blueprint and
   register it.
2. Add the template under `runnify/templates/<area>/`, extending a layout.
3. Add any page styles to `runnify/static/css/pages/` and scripts to
   `runnify/static/js/pages/`.
4. Check the URL appears in `uv run flask --app runnify routes`, add a test, and
   update [routes.md](routes.md).

## Tests and linting

```bash
uv run pytest                # about 280 tests, around a minute
uv run ruff check .          # lint: pycodestyle, pyflakes, imports, bugbear, bandit and more
uv run ruff format .         # format
```

The tests use an in-memory SQLite database, CSRF and rate limits switched off,
and outgoing mail suppressed. `tests/factories.py` builds a run with a recorded
stream and scored songs; `tests/test_demo.py` seeds the full demo and checks the
scoring pipeline finds the songs' hidden effects.

## Demo data

```bash
uv run flask --app runnify demo seed     # asks for the demo account's password
```

Creates `demo@runnify.test` with 36 simulated runs over four months, their
songs and scores, three friends, a pending friend request and a playlist.
Running it again replaces the demo. It refuses to run in production.

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
