"""Runnify: find the songs that make you run faster.

The package exposes :func:`create_app`, the Flask application factory. Run the
development server from the repository root with::

    uv run flask --app runnify db upgrade   # create / migrate the database
    uv run flask --app runnify run --debug
"""

from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from runnify.config import get_config, validate_production_config
from runnify.extensions import csrf, db, limiter, login_manager, mail, migrate
from runnify.security.headers import init_security_headers

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

    if not app.config.get("FIT_STORAGE_DIR"):
        app.config["FIT_STORAGE_DIR"] = str(Path(app.instance_path) / "fit_files")

    if proxies := app.config["PROXY_COUNT"]:
        # trust X-Forwarded-For / -Proto from exactly the proxies we run behind
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR), render_as_batch=True)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    init_security_headers(app)

    # imported here so models and routes bind to the extensions above
    from runnify import models  # noqa: F401  (registers the models and the user loader)
    from runnify.routes import register_blueprints

    register_blueprints(app)

    @app.errorhandler(404)
    def page_not_found(error):
        """Render the custom 404 page."""
        return render_template("404.html"), 404

    @app.errorhandler(429)
    def too_many_requests(error):
        """A rate limit was hit: explain, without revealing which limit or account."""
        message = "Too many attempts. Please wait a few minutes and try again."
        return render_template("errors/error.html", title="Slow down", message=message), 429

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        """A form arrived without a valid CSRF token: send the visitor back to try again."""
        flash("That form expired before it was sent. Please try again.", "error")
        try:  # back to the same page when it can be shown with GET, else home
            app.url_map.bind_to_environ(request.environ).match(request.path, method="GET")
            target = request.path
        except HTTPException:
            target = url_for("main.home")
        return redirect(target, code=303)

    return app
