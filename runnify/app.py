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
login_manager.login_view = "login"


# loading current user
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()

# registering all routes/blueprints
register_blueprints(app)


# error handling
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404

# running the app
if __name__ == "__main__":
    app.run(debug=True)
