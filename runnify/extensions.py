"""Flask extension instances.

They are created here, unbound, so any module can import them without
importing the app; :func:`runnify.create_app` binds them to the application.
"""

from flask_login import LoginManager
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
mail = Mail()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
