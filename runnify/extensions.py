"""Flask extension instances.

They are created here, unbound, so any module can import them without
importing the app; :func:`runnify.create_app` binds them to the application.
"""

import sqlite3

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

# Deterministic constraint names, so Alembic migrations can reliably alter or drop them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)  # storage and switches come from config
mail = Mail()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


@event.listens_for(Engine, "connect")
def _tune_sqlite(dbapi_connection, connection_record):
    """Make SQLite (the default database) safe for the app's background threads.

    WAL lets readers and a writer work at the same time, the busy timeout
    waits for a lock instead of failing with "database is locked", and
    foreign keys are enforced (SQLite leaves them off by default).
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
