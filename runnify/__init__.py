"""Runnify: find the songs that make you run faster.

The package exposes :func:`create_app`, the Flask application factory. Run the
development server from the repository root with::

    uv run flask --app runnify db upgrade   # create / migrate the database
    uv run flask --app runnify run --debug
"""

from pathlib import Path

from flask import Flask, render_template

from runnify.config import Config
from runnify.extensions import db, login_manager, mail, migrate

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def create_app(config_object=Config):
    """Create and configure a Runnify application.

    The database schema is managed by Alembic migrations (``flask db upgrade``),
    not created at start-up.

    Args:
        config_object: Object (or import path) whose upper-case attributes are
            loaded into ``app.config``. Defaults to :class:`runnify.config.Config`.

    Returns:
        The configured :class:`flask.Flask` application.
    """
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR), render_as_batch=True)
    mail.init_app(app)
    login_manager.init_app(app)

    # imported here so models and routes bind to the extensions above
    from runnify import models  # noqa: F401  (registers the models and the user loader)
    from runnify.routes import register_blueprints

    register_blueprints(app)

    @app.errorhandler(404)
    def page_not_found(error):
        """Render the custom 404 page."""
        return render_template("404.html"), 404

    return app
