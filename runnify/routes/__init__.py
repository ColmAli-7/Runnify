"""Route blueprints.

Each module defines one Flask blueprint named ``bp``; :func:`register_blueprints`
attaches them all to the app. See ``docs/routes.md`` for the full URL reference.
"""

from . import (
    auth,
    dashboard,
    friends,
    garmin,
    help,
    insights,
    main,
    playlists,
    runs,
    settings,
    spotify,
)


def register_blueprints(app):
    """Register every Runnify blueprint on ``app``.

    The Spotify blueprint is mounted under ``/spotify``; all others are
    mounted at the site root.
    """
    app.register_blueprint(auth.bp)  # login, registration and password reset
    app.register_blueprint(spotify.bp, url_prefix="/spotify")  # spotify oauth and history import
    app.register_blueprint(garmin.bp)  # garmin account linking
    app.register_blueprint(runs.bp)  # run list and per-run analysis
    app.register_blueprint(settings.bp)  # account management
    app.register_blueprint(dashboard.bp)  # dashboard
    app.register_blueprint(friends.bp)  # friends system
    app.register_blueprint(main.bp)  # homepage
    app.register_blueprint(playlists.bp)  # playlist creator
    app.register_blueprint(insights.bp)  # music insights
    app.register_blueprint(help.bp)  # help and guides
