"""Application configuration.

Values are read from environment variables (loaded from a ``.env`` file via
python-dotenv) with development-friendly fallbacks. See ``.env.example`` for
the full list of variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Flask config object, loaded with ``app.config.from_object(Config)``.

    Attributes:
        SECRET_KEY: Signs session cookies and password-reset tokens.
        SQLALCHEMY_DATABASE_URI: Database URL (``DATABASE_URL``); defaults to
            a local SQLite file in Flask's instance folder.
        MAX_CONTENT_LENGTH: Maximum request body size (Spotify history zips
            can be large).
        HISTORY_BATCH_COMMIT_EVERY: Intended batch size for bulk inserts during
            Spotify history import.
        HISTORY_MIN_OVERLAP_SECONDS: Minimum seconds a song must overlap a run
            to be linked to it.
        MAIL_*: Flask-Mail settings used for password-reset emails.
    """

    SECRET_KEY = os.getenv("SECRET_KEY", "runnify-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///runnify.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # custom limits
    MAX_CONTENT_LENGTH = 600 * 1024 * 1024  # max upload size - like 600mb
    HISTORY_BATCH_COMMIT_EVERY = 1000  # commit frequency for bulk inserts
    HISTORY_MIN_OVERLAP_SECONDS = 1  # min overlap for track matching

    # mail config
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False") == "True"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv(
        "MAIL_DEFAULT_SENDER", "runnify.dev@gmail.com"
    )  # default email sender
