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

import hmac
import secrets
from datetime import UTC, datetime

from flask_login import UserMixin

from runnify.extensions import db, login_manager
from runnify.security.crypto import EncryptedString


def utcnow():
    """Return the current UTC time as a naive ``datetime`` (how timestamps are stored)."""
    return datetime.now(UTC).replace(tzinfo=None)


def new_session_token():
    """Return a fresh random session token (see :meth:`User.get_id`)."""
    return secrets.token_urlsafe(32)


class User(db.Model, UserMixin):
    """A Runnify account.

    Stores login details plus the credentials needed to talk to Spotify
    (OAuth tokens) and Garmin Connect. Third-party credentials are encrypted
    at rest (:class:`~runnify.security.crypto.EncryptedString`).
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    spotify_token = db.Column(EncryptedString)
    spotify_refresh_token = db.Column(EncryptedString)
    spotify_expires_at = db.Column(db.Integer)
    garmin_username = db.Column(db.String)
    garmin_tokens = db.Column(EncryptedString)  # Garmin session tokens (never a password)
    garmin_password = db.Column(EncryptedString)  # legacy: erased by the next sync
    garmin_sync_state = db.Column(db.String(16))  # "syncing", "ok" or "failed"
    garmin_sync_message = db.Column(db.String(200))
    garmin_last_synced_at = db.Column(db.DateTime)

    # Spotify history import progress: "importing", "ok" or "failed"
    history_import_state = db.Column(db.String(16))
    history_import_message = db.Column(db.String(200))
    history_imported_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    # consent: terms + privacy policy, and explicit consent to process run and
    # heart-rate data (GDPR Art. 9); policy_version is the version agreed to
    terms_accepted_at = db.Column(db.DateTime)
    data_consent_at = db.Column(db.DateTime)
    policy_version = db.Column(db.String(10))

    # brute-force protection: consecutive failed sign-ins and the lock they caused
    failed_login_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    locked_until = db.Column(db.DateTime)

    # part of every session and remember-me cookie; rotating it signs out every device
    session_token = db.Column(db.String(64), nullable=False, default=new_session_token)

    # two-step verification (authenticator app); see runnify.security.two_factor
    totp_secret = db.Column(EncryptedString)
    totp_enabled_at = db.Column(db.DateTime)
    totp_last_step = db.Column(
        db.Integer
    )  # last accepted 30-second step, so codes can't be replayed

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

    def get_id(self):
        """Identify the user in session cookies as ``"<id>:<session token>"``.

        Cookies minted before the token last rotated no longer match, so
        rotating it (on password change, or "sign out everywhere") ends every
        other session, remember-me cookies included.
        """
        return f"{self.id}:{self.session_token}"

    def rotate_session_token(self):
        """Invalidate every existing session for this user."""
        self.session_token = new_session_token()

    @property
    def has_current_consent(self):
        """Whether the user has agreed to the current terms and data processing."""
        from flask import current_app

        return (
            bool(self.data_consent_at)
            and self.policy_version == current_app.config["POLICY_VERSION"]
        )

    def record_consent(self):
        """Record agreement to the current terms, privacy policy and data processing."""
        from flask import current_app

        self.terms_accepted_at = self.data_consent_at = utcnow()
        self.policy_version = current_app.config["POLICY_VERSION"]

    @property
    def two_factor_enabled(self):
        """Whether sign-in needs an authenticator code as well as the password."""
        return self.totp_enabled_at is not None and bool(self.totp_secret)


@login_manager.user_loader
def load_user(session_id):
    """Flask-Login callback: load the user whose id *and* current session token match the cookie."""
    user_id, _, token = session_id.partition(":")
    if not user_id.isdigit() or not token:
        return None
    user = db.session.get(User, int(user_id))
    if user is None or not hmac.compare_digest(user.session_token, token):
        return None
    return user


class Run(db.Model):
    """A running activity imported from Garmin Connect.

    ``distance`` is in metres, ``duration`` in seconds and ``avg_pace`` in
    minutes per km. Second-by-second samples live in :class:`RunStream`;
    ``fit_file_path`` only exists on runs imported before streams did.
    """

    __tablename__ = "runs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    activity_id = db.Column(db.String, nullable=False)
    date_time = db.Column(db.DateTime, default=utcnow)
    distance = db.Column(db.Float)
    duration = db.Column(db.Integer)
    avg_hr = db.Column(db.Integer)
    avg_pace = db.Column(db.Float)
    fit_file_path = db.Column(db.String)

    user = db.relationship("User", back_populates="runs")  # link run to user
    analysis = db.relationship("RunSongAnalysis", back_populates="run")  # link run to analysis


class Song(db.Model):
    """A Spotify track, keyed by its Spotify track id.

    ``duration`` (seconds) is learned from plays that ran to the end of the
    track; it is used to fit playlists to a target length.
    """

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
    ``time_played`` its length in seconds. ``skipped`` records whether the
    runner skipped the track (``None`` when Spotify didn't say).
    """

    __tablename__ = "user_song_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    song_id = db.Column(db.String, db.ForeignKey("songs.id"))
    played_at = db.Column(db.DateTime)
    time_played = db.Column(db.Integer)
    run_id = db.Column(db.Integer, db.ForeignKey("runs.id"), index=True)
    skipped = db.Column(db.Boolean)

    user = db.relationship("User", back_populates="song_history")
    song = db.relationship("Song", back_populates="song_history")
    analysis = db.relationship(
        "RunSongAnalysis", back_populates="user_song"
    )  # link to analysis table


class RunSongAnalysis(db.Model):
    """The measured effect of one song play within one run (see ``services/scoring.py``).

    ``performance_score`` is 0-100, where 50 is the runner's usual pace at that
    point of the run; ``pace_delta`` is the same effect in seconds per km
    (positive = faster), ``hr_delta`` the heart-rate change in bpm, ``seconds``
    the moving time measured and ``position`` where in the run the song started
    (0 to 1). ``method_version`` identifies the scoring method that produced it.
    """

    __tablename__ = "run_song_analysis"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("runs.id"), index=True)
    user_song_id = db.Column(db.Integer, db.ForeignKey("user_song_history.id"))
    performance_score = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    pace_delta = db.Column(db.Float)
    hr_delta = db.Column(db.Float)
    seconds = db.Column(db.Integer)
    position = db.Column(db.Float)
    method_version = db.Column(db.Integer)

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


class RecoveryCode(db.Model):
    """A single-use two-step-verification recovery code, stored as a SHA-256 hash."""

    __tablename__ = "recovery_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash = db.Column(db.String(64), nullable=False)
    used_at = db.Column(db.DateTime)


class SecurityEvent(db.Model):
    """A security-relevant event on an account (sign-ins, password and 2FA changes, ...).

    IP addresses are stored truncated (IPv4 /24, IPv6 /48) and user agents
    shortened, so the log can't pinpoint anyone; entries expire after 90 days.
    """

    __tablename__ = "security_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = db.Column(db.String(40), nullable=False)
    ip_prefix = db.Column(db.String(45))
    user_agent = db.Column(db.String(160))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)


class RunStream(db.Model):
    """A run's pace and heart-rate samples, compressed (see :mod:`runnify.services.streams`)."""

    __tablename__ = "run_streams"

    run_id = db.Column(db.Integer, db.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False)  # UTC time of the first sample
    sample_count = db.Column(db.Integer, nullable=False)
    samples = db.Column(db.LargeBinary, nullable=False)


class Playlist(db.Model):
    """A playlist built from the runner's proven songs (see :mod:`runnify.services.playlists`)."""

    __tablename__ = "playlists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = db.Column(db.String(100), nullable=False)
    session = db.Column(db.String(20), nullable=False)  # easy, tempo, long, race or intervals
    target_minutes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    spotify_playlist_id = db.Column(db.String(64))
    spotify_url = db.Column(db.String(200))

    tracks = db.relationship(
        "PlaylistTrack",
        order_by="PlaylistTrack.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def total_seconds(self):
        return sum(track.seconds for track in self.tracks)


class PlaylistTrack(db.Model):
    """One position in a playlist, with the evidence it was chosen on."""

    __tablename__ = "playlist_tracks"

    playlist_id = db.Column(
        db.Integer, db.ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )
    position = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.String, db.ForeignKey("songs.id"), nullable=False)
    seconds = db.Column(db.Integer, nullable=False)  # track length used to fit the target time
    lift = db.Column(db.Float)  # s/km effect when the playlist was built
    plays = db.Column(db.Integer)  # scored plays behind that effect

    song = db.relationship("Song")
