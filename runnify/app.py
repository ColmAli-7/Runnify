"""Runnify application entry point.

Creates the Flask app, wires up the database, mail and login extensions,
creates any missing tables and registers every route blueprint.

Run from the repository root with::

    uv run flask --app runnify/app.py run --debug

Imports in this package are flat (``from models import ...``), so the
``runnify/`` directory must be on ``sys.path``. ``flask --app runnify/app.py``
and ``python runnify/app.py`` both take care of that automatically.
"""

from flask import Flask, render_template
from models import db, User
from flask_login import LoginManager
from routes import register_blueprints
from config import Config
from flask_mail import Mail

app = Flask(__name__)
app.config.from_object(Config)  # load everything from config.py

# configure extensions
db.init_app(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


# loading current user
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login callback: load the ``User`` stored in the session cookie."""
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()

# registering all routes/blueprints
register_blueprints(app)


# error handling
@app.errorhandler(404)
def page_not_found(error):
    """Render the custom 404 page."""
    return render_template("404.html"), 404

# running the app
if __name__ == "__main__":
    app.run(debug=False)
