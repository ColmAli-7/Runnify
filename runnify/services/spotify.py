"""Spotify Web API access: OAuth and authenticated clients.

Every OAuth helper gets its own in-memory token cache. spotipy's default
caches tokens in a ``.cache`` file in the working directory, which on a server
would be shared by every user. Requests time out instead of hanging a worker.
"""

import time

import spotipy
from flask import current_app
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from runnify.extensions import db

REQUEST_TIMEOUT = 10  # seconds
REFRESH_MARGIN = 60  # refresh tokens that expire within this many seconds


def oauth():
    """Return a ``SpotifyOAuth`` helper configured from the app's ``SPOTIFY_*`` settings."""
    config = current_app.config
    return SpotifyOAuth(
        client_id=config["SPOTIFY_CLIENT_ID"],
        client_secret=config["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=config["SPOTIFY_REDIRECT_URI"],
        scope=config["SPOTIFY_SCOPE"],
        cache_handler=MemoryCacheHandler(),
        open_browser=False,
        requests_timeout=REQUEST_TIMEOUT,
    )


def authorize_url(state):
    """Return Spotify's consent-page URL carrying our anti-CSRF ``state``."""
    return oauth().get_authorize_url(state=state)


def exchange_code(code):
    """Exchange an authorisation ``code`` for a token-info dict.

    ``code`` must be non-empty: given no code, spotipy falls back to
    interactive prompts that would block a server worker.
    """
    if not code:
        raise ValueError("an authorisation code is required")
    helper = oauth()
    helper.get_access_token(code, as_dict=False, check_cache=False)
    return helper.cache_handler.get_cached_token()


def save_tokens(user, token_info):
    """Store a token-info dict on ``user`` (encrypted by the model)."""
    user.spotify_token = token_info["access_token"]
    user.spotify_refresh_token = token_info.get("refresh_token") or user.spotify_refresh_token
    user.spotify_expires_at = int(token_info["expires_at"])


def client_for(user):
    """Return an authenticated ``spotipy.Spotify`` client for ``user``, refreshing if needed.

    Returns ``None`` if the user has not connected Spotify.
    """
    if not user.spotify_token or not user.spotify_refresh_token:
        return None
    if (user.spotify_expires_at or 0) - int(time.time()) < REFRESH_MARGIN:
        save_tokens(user, oauth().refresh_access_token(user.spotify_refresh_token))
        db.session.commit()
    return spotipy.Spotify(auth=user.spotify_token, requests_timeout=REQUEST_TIMEOUT)


def disconnect(user):
    """Forget the user's Spotify tokens."""
    user.spotify_token = user.spotify_refresh_token = user.spotify_expires_at = None
