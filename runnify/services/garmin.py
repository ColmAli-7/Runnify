"""Garmin Connect activity sync."""

import os
import time
import zipfile
from datetime import datetime

from garminconnect import Garmin

from runnify.extensions import db
from runnify.models import Run

FIT_DIR = "fit_files"
DOWNLOAD_FORMAT = Garmin.ActivityDownloadFormat.ORIGINAL  # garmin format for .fit files


def fetch_and_store_garmin_activities(user):
    """Download all new running activities for ``user`` and save them as ``Run`` rows.

    Pages through the user's Garmin activity list 20 at a time, skips
    activities already stored and anything that is not a run, downloads each
    activity's original ``.fit`` file into ``FIT_DIR`` and commits one batch
    per page. Intended to run in a background thread inside an app context.

    Args:
        user: The ``User`` whose Garmin credentials should be used.
    """
    email = user.garmin_username
    password = user.garmin_password  # decrypted by the model
    client = Garmin(email, password)
    client.login()  # authenticate with garmin
    os.makedirs(FIT_DIR, exist_ok=True)

    page_size = 20  # number of activities to fetch per request
    start = 0  # pagination index
    processed = 0
    total = 1

    while True:
        # fetch batch of activities
        activities = client.get_activities(start, page_size)
        if not activities:  # stop when no more data
            break
        total = max(total, start + len(activities))
        for act in activities:
            activity_id = str(act["activityId"])
            existing = Run.query.filter_by(user_id=user.id, activity_id=activity_id).first()
            if existing:
                print(f"Skipping duplicate activity {activity_id}")
                continue  # avoid existing entries
            if "running" not in act["activityType"]["typeKey"]:
                print(f"Skipping non-running activity {activity_id}")
                continue  # only store running sessions

            start_time = datetime.strptime(act["startTimeGMT"], "%Y-%m-%d %H:%M:%S")
            duration = int(act.get("duration", 0))
            distance = float(act.get("distance", 0))
            avg_hr = act.get("averageHR")
            avg_speed = act.get("averageSpeed", 0.0)
            avg_pace = (1000 / avg_speed / 60) if avg_speed > 0 else None  # convert to min/km

            zip_filename = os.path.join(FIT_DIR, f"{activity_id}_ACTIVITY.zip")
            fit_filename = os.path.join(FIT_DIR, f"{activity_id}_ACTIVITY.fit")

            try:
                # download the activity as a zip and extract the fit file
                fit_zip_data = client.download_activity(activity_id, dl_fmt=DOWNLOAD_FORMAT)
                time.sleep(1)
                with open(zip_filename, "wb") as f:
                    f.write(fit_zip_data)
                with zipfile.ZipFile(zip_filename, "r") as zip_ref:
                    zip_ref.extractall(FIT_DIR)
                os.remove(zip_filename)
                fit_path = fit_filename if os.path.exists(fit_filename) else None
            except Exception as e:
                print(f"Could not download FIT for {activity_id}: {e}")
                fit_path = None  # handle failed downloads

            run = Run(
                user_id=user.id,
                activity_id=activity_id,
                date_time=start_time,
                distance=distance,
                duration=duration,
                avg_hr=avg_hr,
                avg_pace=avg_pace,
                fit_file_path=(fit_path if fit_path else activity_id),  # store fit file path or id
            )
            db.session.add(run)
            processed += 1  # track total saved activities
        db.session.commit()
        start += page_size  # move to next batch
