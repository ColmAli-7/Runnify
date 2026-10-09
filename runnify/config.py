"""Application configuration.

Settings come from environment variables; a local ``.env`` file is loaded with
python-dotenv. ``APP_ENV`` selects the profile: ``development`` (the default)
or ``production``. Production refuses to start with missing or weak secrets
(see :func:`validate_production_config`). ``.env.example`` documents every
variable.
"""

import os
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def env_bool(name, default=False):
    """Read a boolean environment variable ("1", "true", "yes" or "on" mean true)."""
    value = os.getenv(name, "").strip().lower()
    return default if not value else value in {"1", "true", "yes", "on"}


def env_int(name, default):
    """Read an integer environment variable."""
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def env_list(name):
    """Read a comma-separated environment variable into a list of strings."""
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def database_url():
    """Return ``DATABASE_URL``; SQLite (``runnify/instance/runnify.db``) when unset.

    SQLite is the default while Runnify is being tested; PostgreSQL works too.
    PostgreSQL URLs are pinned to the installed psycopg2 driver:
    Hosts hand out ``postgres://`` or ``postgresql://`` URLs; SQLAlchemy 2.1
    maps a bare ``postgresql://`` to psycopg 3, which is not installed.
    """
    url = os.getenv("DATABASE_URL", "sqlite:///runnify.db")
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg2://" + url.removeprefix(scheme)
    return url


class Config:
    """Settings shared by every environment.

    Attributes:
        SECRET_KEY: Signs session cookies and security tokens.
        SQLALCHEMY_DATABASE_URI: Database URL (``DATABASE_URL``); defaults to a
            local SQLite file in Flask's instance folder.
        PUBLIC_BASE_URL: The site's public origin, used for links in emails so
            they never depend on a request's ``Host`` header.
        TRUSTED_HOSTS: ``Host`` header allow-list (``ALLOWED_HOSTS``).
        PROXY_COUNT: Reverse proxies in front of the app, trusted for the
            client IP and scheme.
        MAX_CONTENT_LENGTH: Maximum request body size (``MAX_UPLOAD_MB``).
        HISTORY_BATCH_SIZE: Rows added per commit during bulk inserts in the
            Spotify history import.
        HISTORY_MIN_OVERLAP_SECONDS: Minimum seconds a song must overlap a run
            to be linked to it.
        FERNET_KEY: Key used to encrypt stored third-party credentials.
        SPOTIFY_*: Spotify OAuth client settings.
        MAIL_*: Flask-Mail settings; with no ``MAIL_SERVER`` emails are logged
            instead of sent.
    """

    ENV_NAME = "base"

    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}  # survive dropped idle connections
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # where the site lives and who is allowed to talk to it
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    TRUSTED_HOSTS = env_list("ALLOWED_HOSTS") or None
    PROXY_COUNT = env_int("PROXY_COUNT", 0)

    # session and remember-me cookies: never readable by scripts, never sent cross-site
    SESSION_COOKIE_NAME = "runnify_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    REMEMBER_COOKIE_NAME = "runnify_remember"
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = False

    # Content-Security-Policy is report-only until every legacy template is rebuilt
    # without CDN scripts and inline JavaScript; then it is enforced
    CSP_REPORT_ONLY = True

    # rate limits (Flask-Limiter syntax). Use a shared store such as Redis in production
    # (RATELIMIT_STORAGE_URI=redis://...) so limits hold across every worker.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_STRATEGY = "moving-window"
    RATELIMIT_HEADERS_ENABLED = True
    RATE_LIMIT_LOGIN = "10 per minute; 50 per hour"
    RATE_LIMIT_REGISTER = "5 per hour"
    RATE_LIMIT_PASSWORD_RESET = "5 per hour"  # noqa: S105  (a limit, not a password)
    RATE_LIMIT_ACCOUNT_CHANGE = "10 per hour"
    RATE_LIMIT_GARMIN_CONNECT = "5 per hour"
    RATE_LIMIT_GARMIN_SYNC = "6 per hour"
    RATE_LIMIT_UPLOAD = "10 per hour"
    RATE_LIMIT_SEARCH = "30 per minute"
    RATE_LIMIT_SPOTIFY_EXPORT = "10 per hour"

    # account lockout: after this many consecutive failed sign-ins the account is locked,
    # first for LOGIN_LOCKOUT_MINUTES, doubling with each further failure (max 24 hours)
    LOGIN_LOCKOUT_THRESHOLD = 5
    LOGIN_LOCKOUT_MINUTES = 15

    # bump when the terms or privacy policy change materially; users then re-confirm
    POLICY_VERSION = "2026-10"
    POLICY_UPDATED = "9 October 2026"
    # who runs the site, shown on the legal pages
    OPERATOR_NAME = os.getenv("OPERATOR_NAME", "Runnify")
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "runnify.dev@gmail.com")
    LEGAL_JURISDICTION = os.getenv("LEGAL_JURISDICTION", "Ireland")

    # password-reset links are single-use and expire after this many seconds
    PASSWORD_RESET_MAX_AGE = 30 * 60

    # CSRF tokens are tied to the session, so they need no separate expiry
    WTF_CSRF_TIME_LIMIT = None

    # uploads and imports; FIT files default to <instance folder>/fit_files
    FIT_STORAGE_DIR = os.getenv("FIT_STORAGE_DIR")
    MAX_CONTENT_LENGTH = env_int("MAX_UPLOAD_MB", 100) * 1024 * 1024
    UPLOAD_TMP_DIR = os.getenv("UPLOAD_TMP_DIR")  # default: <instance folder>/uploads
    HISTORY_BATCH_SIZE = 1000  # rows per commit for bulk inserts
    # an archive breaking any of these is refused before parsing (zip-bomb protection)
    HISTORY_MAX_ENTRIES = 1000
    HISTORY_MAX_UNCOMPRESSED_MB = 2048
    HISTORY_MAX_COMPRESSION_RATIO = 100
    HISTORY_MIN_OVERLAP_SECONDS = 1  # min overlap for track matching

    # integrations
    FERNET_KEY = os.getenv("FERNET_KEY")
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
    SPOTIFY_SCOPE = os.getenv("SPOTIFY_SCOPE")

    # mail
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = env_int("MAIL_PORT", 587)
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "runnify.dev@gmail.com")


class DevelopmentConfig(Config):
    """Local development. A missing ``SECRET_KEY`` is replaced by a random one per process."""

    ENV_NAME = "development"
    SECRET_KEY = Config.SECRET_KEY or secrets.token_hex(32)
    TEMPLATES_AUTO_RELOAD = True  # pick up template edits without restarting the server


class ProductionConfig(Config):
    """Production: HTTPS-only cookies and one trusted proxy (Render) by default."""

    ENV_NAME = "production"
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PROXY_COUNT = env_int("PROXY_COUNT", 1)


class TestConfig(Config):
    """Configuration for the test suite: in-memory database, dummy credentials, no real mail."""

    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key"  # noqa: S105  (tests only)
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    PUBLIC_BASE_URL = "http://localhost"
    FERNET_KEY = "x3HpWkM5yMTkNmGF9v8xB2o1C0Gq4WqY7d0Zr6Jc1sE="  # dummy key, tests only
    SPOTIFY_CLIENT_ID = "test-client-id"
    SPOTIFY_CLIENT_SECRET = "test-client-secret"  # noqa: S105  (tests only)
    SPOTIFY_REDIRECT_URI = "http://127.0.0.1:5000/spotify/callback"
    SPOTIFY_SCOPE = "user-read-email"
    MAIL_SUPPRESS_SEND = True
    WTF_CSRF_ENABLED = False  # tests post forms directly; test_csrf.py turns it back on
    RATELIMIT_ENABLED = False  # test_rate_limits.py turns limits back on


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestConfig,
}


def get_config(name=None):
    """Return the config class for ``name`` (default: the ``APP_ENV`` environment variable)."""
    name = (name or os.getenv("APP_ENV") or "development").strip().lower()
    try:
        return CONFIGS[name]
    except KeyError:
        raise RuntimeError(f"Unknown APP_ENV {name!r}; expected one of {sorted(CONFIGS)}") from None


def validate_production_config(config):
    """Return a list of problems that make ``config`` unsafe to run in production."""
    problems = []
    if len(config.get("SECRET_KEY") or "") < 32:
        problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
    try:
        Fernet((config.get("FERNET_KEY") or "").encode())
    except ValueError:
        problems.append("FERNET_KEY must be set to a valid Fernet key")
    if not (config.get("PUBLIC_BASE_URL") or "").startswith("https://"):
        problems.append("PUBLIC_BASE_URL must be the site's https:// origin")
    if not config.get("TRUSTED_HOSTS"):
        problems.append("ALLOWED_HOSTS must list the host names the site is served on")
    return problems
