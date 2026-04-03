from .auth import auth
from .spocon import spocon
from .garcon import garcon
from .get_activities import get_activities
from .manage import manage
from .dash import dash
from .friends import friends
from .main import main
from .playlist import playlist
from .music_insights import music_insights
from .help import help


# register all app blueprints
def register_blueprints(app):
    app.register_blueprint(auth)  # login and registration routes
    app.register_blueprint(spocon, url_prefix="/spotify")  # spotify routes
    app.register_blueprint(garcon)  # garmin routes
    app.register_blueprint(get_activities)  # activity retrieval
    app.register_blueprint(manage)  # account management
    app.register_blueprint(dash)  # dashboard routes
    app.register_blueprint(friends)  # friends system
    app.register_blueprint(main)  # homepage and misc routes
    app.register_blueprint(playlist)  # playlist generation
    app.register_blueprint(music_insights)  # music analytics
    app.register_blueprint(help)  # help and guides