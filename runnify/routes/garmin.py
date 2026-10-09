"""Garmin Connect account linking.

Garmin passwords are encrypted with the app's ``FERNET_KEY`` before storage.
"""

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
from runnify.extensions import db
from runnify.models import User
from cryptography.fernet import Fernet
from runnify.services.garmin import fetch_and_store_garmin_activities

bp = Blueprint("garmin", __name__)  # garmin connection routes


def _fernet():
    """Return the Fernet cipher used to encrypt stored Garmin passwords."""
    return Fernet(current_app.config["FERNET_KEY"].encode())


@bp.route("/garmin", methods=["GET", "POST"])
@login_required
def garmin():
    """Link a Garmin account.

    On POST, test-logs in to Garmin Connect with the submitted credentials,
    stores the email and encrypted password on the user, then starts a
    background thread that imports all running activities.
    """
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        try:
            client = Garmin(email, password)  # create garmin client
            client.login()  # test login
            fernet = _fernet()
            encrypted_pw = fernet.encrypt(
                password.encode()
            ).decode()  # encrypt password for storage
            current_user.garmin_username = email
            current_user.garmin_password = encrypted_pw
            db.session.commit()
            app = current_app._get_current_object()  # get flask app context

            def background_job(user_id, app):
                """Run the Garmin sync for ``user_id`` inside an app context."""
                with app.app_context():  # allow db access in thread
                    user = db.session.get(User, user_id)
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
            flash(f"Garmin login failed: Incorrect Details or API Failed: {e}", "danger")
            return render_template("garmin.html")
    return render_template("garmin.html")
