"""Each song's page: what one song did across the runner's runs (see :mod:`runnify.services.songs`)."""

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from runnify.services import songs

bp = Blueprint("songs", __name__)


@bp.route("/songs/<song_id>")
@login_required
def detail(song_id):
    """One song: its lift and evidence, a dot per measured play with a trend line, and its runs.

    Songs are shared between runners, so one the runner never heard during a run is a 404.
    """
    record = songs.song_record(current_user.id, song_id)
    if record is None:
        abort(404)
    return render_template(
        "songs/detail.html",
        record=record,
        verdict=songs.verdict(record),
        chart=songs.chart(record),
        chart_summary=songs.chart_summary(record),
        trend_note=songs.trend_note(record),
    )
