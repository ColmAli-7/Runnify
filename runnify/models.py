"""SQLAlchemy database models.

Entity overview (see ``docs/architecture.md`` for a diagram):

- ``User`` has many ``Run`` and many ``UserSongHistory`` rows.
- ``UserSongHistory`` links a ``User``, a ``Song`` and (optionally) a ``Run``.
- ``RunSongAnalysis`` links a ``Run`` to a ``UserSongHistory`` row.

``UserSongHistory`` rows are song plays that overlapped one of the user's
runs; ``RunSongAnalysis`` stores the performance score computed for each.
Users are linked to each other through the ``friends`` association table and
``FriendRequest``.
"""

from flask_login import UserMixin
from datetime import datetime, timezone

from runnify.extensions import db, login_manager


def utcnow():
    """Return the current UTC time as a naive ``datetime`` (how timestamps are stored)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model, UserMixin):
    """A Runnify account.

    Stores login details plus the credentials needed to talk to Spotify
    (OAuth tokens) and Garmin Connect (username and a Fernet-encrypted
    password).
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    spotify_token = db.Column(db.String)
    spotify_refresh_token = db.Column(db.String)
    spotify_expires_at = db.Column(db.Integer)
    garmin_username = db.Column(db.String)
    garmin_password = db.Column(db.String)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    runs = db.relationship("Run", back_populates="user")  # link to user runs
    song_history = db.relationship(
        "UserSongHistory", back_populates="user"
    )  # link to user song history

    # friend relationship through association table
    friends = db.relationship(
        "User",
        secondary="friends",
        primaryjoin="User.id==friends.c.user_id",
        secondaryjoin="User.id==friends.c.friend_id",
        backref="friend_of",
    )


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login callback: load the ``User`` stored in the session cookie."""
    return db.session.get(User, int(user_id))


class Run(db.Model):
    """A running activity imported from Garmin Connect.

    ``distance`` is in metres, ``duration`` in seconds and ``avg_pace`` in
    minutes per km. ``fit_file_path`` points at the downloaded ``.fit`` file
    (or holds the Garmin activity id if the download failed).
    """

    __tablename__ = "runs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    activity_id = db.Column(db.String, nullable=False)
    date_time = db.Column(db.DateTime, default=utcnow)
    distance = db.Column(db.Float)
    duration = db.Column(db.Integer)
    avg_hr = db.Column(db.Integer)
    avg_pace = db.Column(db.Float)
    fit_file_path = db.Column(db.String)

    user = db.relationship("User", back_populates="runs")  # link run to user
    analysis = db.relationship(
        "RunSongAnalysis", back_populates="run"
    )  # link run to analysis


class Song(db.Model):
    """A Spotify track, keyed by its Spotify track id."""

    __tablename__ = "songs"

    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String)
    artist = db.Column(db.String)
    duration = db.Column(db.Integer)
    spotify_url = db.Column(db.String)
    tempo = db.Column(db.Float)

    song_history = db.relationship(
        "UserSongHistory", back_populates="song"
    )  # link song to user song history


class UserSongHistory(db.Model):
    """One song play from a user's Spotify history that overlapped a run.

    ``played_at`` is the (UTC) start of the overlapping segment and
    ``time_played`` its length in seconds.
    """

    __tablename__ = "user_song_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    song_id = db.Column(db.String, db.ForeignKey("songs.id"))
    played_at = db.Column(db.DateTime)
    time_played = db.Column(db.Integer)
    run_id = db.Column(db.Integer, db.ForeignKey("runs.id"))

    user = db.relationship("User", back_populates="song_history")
    song = db.relationship("Song", back_populates="song_history")
    analysis = db.relationship(
        "RunSongAnalysis", back_populates="user_song"
    )  # link to analysis table


class RunSongAnalysis(db.Model):
    """The performance score (0-100) of one song play within one run.

    50 means the user ran at their average pace for that run; higher means
    faster. See ``docs/scoring.md``.
    """

    __tablename__ = "run_song_analysis"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("runs.id"))
    user_song_id = db.Column(db.Integer, db.ForeignKey("user_song_history.id"))
    performance_score = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    run = db.relationship("Run", back_populates="analysis")
    user_song = db.relationship(
        "UserSongHistory", back_populates="analysis"
    )  # connect analysis to song history


# association table for user friendships
friends = db.Table(
    "friends",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("friend_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


class FriendRequest(db.Model):
    """A friend request between two users (``pending`` / ``accepted`` / ``declined``)."""

    __tablename__ = "friend_requests"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String, default="pending")  # pending, accepted, or rejected
    timestamp = db.Column(db.DateTime, default=utcnow)

    sender = db.relationship(
        "User", foreign_keys=[sender_id], backref="sent_requests" 
    )  # link sender
    receiver = db.relationship(
        "User", foreign_keys=[receiver_id], backref="received_requests"
    )  # link receiver
