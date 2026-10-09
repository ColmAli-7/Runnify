"""Garmin Connect account linking.

Garmin credentials are encrypted at rest by the ``User`` model.
"""

import threading

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from garminconnect import Garmin

from runnify.extensions import db, limiter
from runnify.models import User
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services.garmin import fetch_and_store_garmin_activities

bp = Blueprint("garmin", __name__)  # garmin connection routes


@bp.route("/garmin", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("GARMIN_CONNECT"), methods=["POST"], key_func=user_or_ip)
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
            current_user.garmin_username = email
            current_user.garmin_password = password  # encrypted by the model
            db.session.commit()
            app = current_app._get_current_object()  # get flask app context

            def background_job(user_id, app):
                """Run the Garmin sync for ``user_id`` inside an app context."""
                with app.app_context():  # allow db access in thread
                    user = db.session.get(User, user_id)
                    if user:
                        print(f"Starting Garmin sync for {user.email}")
                        fetch_and_store_garmin_activities(user)  # fetch all user activities
                        db.session.commit()
                        print(f"Finished Garmin sync for {user.email}")

            threading.Thread(
                target=background_job, args=(current_user.id, app)
            ).start()  # run sync in background
            flash("Garmin connected! Activities are syncing in the background.", "success")
            return redirect(url_for("dash.dashboard"))
        except Exception as e:  # login or api failure
            flash(f"Garmin login failed: Incorrect Details or API Failed: {e}", "danger")
            return render_template("garmin.html")
    return render_template("garmin.html")
