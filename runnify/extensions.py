"""Flask extension instances.

They are created here, unbound, so any module can import them without
importing the app; :func:`runnify.create_app` binds them to the application.
"""

from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import MetaData

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
mail = Mail()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
