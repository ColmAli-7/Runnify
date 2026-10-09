# Deploying to Render

Runnify runs as one Render **Web Service** (Python) with a **Render Postgres**
database. SQLite on a persistent disk also works for a small private beta.

## 1. A production web server

Flask's built-in server is for development only. Production needs a WSGI
server such as gunicorn, which is **not yet a dependency**. Add it once:

```bash
uv add gunicorn
```

## 2. The database

**Render Postgres (recommended).** Create a database, then copy its *Internal
Database URL* into the web service's `DATABASE_URL`. `postgres://` and
`postgresql://` URLs are both accepted.

**SQLite on a disk (small scale only).** Attach a persistent disk (paid plans),
mounted at, say, `/var/data`, and set `DATABASE_URL=sqlite:////var/data/runnify.db`.
Without a disk, the file is wiped on every deploy. Run a single instance.

## 3. The web service

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install uv && uv sync --frozen --no-dev && uv run flask --app runnify db upgrade` |
| Start command | `uv run gunicorn "runnify:create_app()" --workers 2 --threads 4 --bind 0.0.0.0:$PORT` |
| Health check path | `/login` |

The build command applies any new migrations before each deploy goes live.

## 4. Environment variables

The app refuses to start in production unless the first five are set safely.

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `SECRET_KEY` | 32+ random characters: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FERNET_KEY` | A Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Keep a copy somewhere safe: losing it means every user has to reconnect Garmin and Spotify |
| `PUBLIC_BASE_URL` | `https://<your-service>.onrender.com`, or your own domain |
| `ALLOWED_HOSTS` | `<your-service>.onrender.com` plus any custom domain, comma-separated |
| `DATABASE_URL` | From step 2 |
| `RATELIMIT_STORAGE_URI` | A Render Key Value (Redis) URL, so rate limits and lockouts hold across workers. Without it each worker counts separately |
| `OPERATOR_NAME` | The person or company running the site; it appears in the privacy policy as the data controller |
| `CONTACT_EMAIL` | Where users write about their data |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | An SMTP provider, for password resets and security notices |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_SCOPE` | From the Spotify developer dashboard; scope `playlist-modify-private` |
| `SPOTIFY_REDIRECT_URI` | `https://<your-domain>/spotify/callback`, registered in the Spotify dashboard exactly as written |

`PROXY_COUNT` defaults to 1 in production, which is right for Render's single
proxy. Sessions and the remember-me cookie are `Secure`, `HttpOnly` and
`SameSite=Lax`, and HSTS is sent over HTTPS.

## 5. After the first deploy

- Sign up, connect Garmin and upload a Spotify history zip to check the
  background jobs, the email settings and the Spotify callback.
- Rotating `FERNET_KEY`: set `FERNET_KEYS` to `new-key,old-key`; new values use
  the first key and old values still decrypt. Remove the old key once every
  user's tokens have been re-saved (each Garmin sync re-saves them).
- After a scoring change, re-measure every run with the Render shell:
  `uv run flask --app runnify scores rebuild`.

## Things to know

- **Background work runs inside the web workers** (Garmin syncs and history
  imports use threads). A deploy or restart in the middle of one interrupts it;
  the user can start it again from Connections or Import. A job queue is the
  next step if usage grows.
- **Uploads** are written to `runnify/instance/uploads/` (override with
  `UPLOAD_TMP_DIR`) and deleted as soon as they are read, so the ephemeral disk
  is fine for them.
- The demo seed command refuses to run in production.
