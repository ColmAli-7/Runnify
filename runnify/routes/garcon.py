import threading
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user
from garminconnect import Garmin
from models import db, User
from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv
from functions.garmin_service import fetch_and_store_garmin_activities

load_dotenv()
fernet = Fernet(os.environ["FERNET_KEY"].encode())  # encryption for garmin passwords
garcon = Blueprint("garmin", __name__)  # garmin connection routes


@garcon.route("/garmin", methods=["GET", "POST"])
@login_required
def garmin():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        try:
            client = Garmin(email, password)  # create garmin client
            client.login()  # test login
            encrypted_pw = fernet.encrypt(
                password.encode()
            ).decode()  # encrypt password for storage
            current_user.garmin_username = email
            current_user.garmin_password = encrypted_pw
            db.session.commit()
            app = current_app._get_current_object()  # get flask app context

            def background_job(user_id, app):
                with app.app_context():  # allow db access in thread
                    user = User.query.get(user_id)
                    if user:
                        print(f"Starting Garmin sync for {user.email}")
                        fetch_and_store_garmin_activities(
                            user, fernet
                        )  # fetch all user activities
                        db.session.commit()
                        print(f"Finished Garmin sync for {user.email}")

            threading.Thread(
                target=background_job, args=(current_user.id, app)
            ).start()  # run sync in background
            flash(
                "Garmin connected! Activities are syncing in the background.", "success"
            )
            return redirect(url_for("dash.dashboard"))
        except Exception as e:  # login or api failure
            flash(f"Garmin login failed: Incorrect Details or API Failed", "danger")
            return render_template("garmin.html")
    return render_template("garmin.html")
