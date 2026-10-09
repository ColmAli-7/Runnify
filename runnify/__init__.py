"""Runnify: find the songs that make you run faster.

The package exposes :func:`create_app`, the Flask application factory. Run the
development server from the repository root with::

    uv run flask --app runnify db upgrade   # create / migrate the database
    uv run flask --app runnify run --debug
"""

from pathlib import Path

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from runnify.config import get_config, validate_production_config
from runnify.extensions import db, login_manager, mail, migrate

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def create_app(config_object=None):
    """Create and configure a Runnify application.

    The database schema is managed by Alembic migrations (``flask db upgrade``),
    not created at start-up.

    Args:
        config_object: Object (or import path) whose upper-case attributes are
            loaded into ``app.config``. Defaults to the profile named by the
            ``APP_ENV`` environment variable (see :func:`runnify.config.get_config`).

    Returns:
        The configured :class:`flask.Flask` application.

    Raises:
        RuntimeError: In production, when the configuration is unsafe.
    """
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    if app.config["ENV_NAME"] == "production":
        problems = validate_production_config(app.config)
        if problems:
            raise RuntimeError("Refusing to start in production:\n- " + "\n- ".join(problems))

    if proxies := app.config["PROXY_COUNT"]:
        # trust X-Forwarded-For / -Proto from exactly the proxies we run behind
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies)

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
