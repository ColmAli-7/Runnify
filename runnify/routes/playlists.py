"""The playlist creator: build, view, send to Spotify and delete playlists."""

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from runnify.extensions import db, limiter
from runnify.forms import PlaylistForm, first_error
from runnify.models import Playlist
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.services import playlists as playlist_service

bp = Blueprint("playlists", __name__)


def _own_playlist(playlist_id):
    playlist = db.session.get(Playlist, playlist_id)
    if playlist is None or playlist.user_id != current_user.id:
        abort(404)
    return playlist


@bp.route("/playlists", methods=["GET", "POST"])
@login_required
def index():
    """Show the builder and saved playlists; on POST, build and save a new playlist."""
    form = PlaylistForm()
    if form.validate_on_submit():
        result = playlist_service.plan(
            current_user.id, form.session.data, form.minutes.data, form.include_untested.data
        )
        if not result.tracks:
            flash(result.note, "info")
        else:
            playlist = playlist_service.save(current_user, result)
            db.session.commit()
            if result.note:
                flash(result.note, "info")
            return redirect(url_for("playlists.detail", playlist_id=playlist.id))
    elif form.errors:
        flash(first_error(form), "error")
    saved = (
        Playlist.query.filter_by(user_id=current_user.id).order_by(Playlist.created_at.desc()).all()
    )
    return render_template("playlist.html", form=form, saved=saved)


@bp.route("/playlists/<int:playlist_id>")
@login_required
def detail(playlist_id):
    """Show one playlist's tracks and the evidence behind each."""
    return render_template("playlist_detail.html", playlist=_own_playlist(playlist_id))


@bp.route("/playlists/<int:playlist_id>/spotify", methods=["POST"])
@login_required
@limiter.limit(limit_from_config("SPOTIFY_EXPORT"), key_func=user_or_ip)
def send_to_spotify(playlist_id):
    """Create the playlist in the user's Spotify account (as a private playlist)."""
    playlist = _own_playlist(playlist_id)
    try:
        playlist_service.send_to_spotify(current_user, playlist)
    except playlist_service.SpotifyExportError as error:
        flash(str(error), "error")
    else:
        db.session.commit()
        flash("Saved to your Spotify library as a private playlist.", "success")
    return redirect(url_for("playlists.detail", playlist_id=playlist.id))


@bp.route("/playlists/<int:playlist_id>/delete", methods=["POST"])
@login_required
def delete(playlist_id):
    """Delete a playlist from Runnify (a copy already in Spotify is kept)."""
    db.session.delete(_own_playlist(playlist_id))
    db.session.commit()
    flash("Playlist deleted.", "info")
    return redirect(url_for("playlists.index"))
