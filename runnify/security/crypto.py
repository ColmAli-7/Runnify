"""Encryption at rest for third-party credentials.

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256). ``FERNET_KEYS``
may list several comma-separated keys, newest first: new values are encrypted
with the first key and old values still decrypt with any of them, which allows
rotating keys without downtime. ``FERNET_KEY`` alone works too.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app
from sqlalchemy.types import String, TypeDecorator

FERNET_PREFIX = "gAAAAA"  # every Fernet token starts with the version byte and timestamp


def fernet():
    """Return the app's (multi-)Fernet cipher built from ``FERNET_KEYS`` / ``FERNET_KEY``."""
    config = current_app.config
    keys = [k.strip() for k in (config.get("FERNET_KEYS") or "").split(",") if k.strip()]
    if not keys and config.get("FERNET_KEY"):
        keys = [config["FERNET_KEY"]]
    if not keys:
        raise RuntimeError("FERNET_KEY is not configured; it is needed to store credentials")
    return MultiFernet([Fernet(key.encode()) for key in keys])


def encrypt(value):
    """Encrypt a string."""
    return fernet().encrypt(value.encode()).decode()


def decrypt(token):
    """Decrypt a string produced by :func:`encrypt`."""
    return fernet().decrypt(token.encode()).decode()


class EncryptedString(TypeDecorator):
    """A string column stored encrypted; reads and writes look like plain strings in Python.

    Values written before encryption was introduced are returned as they are
    (and encrypted the next time they are saved); anything that looks like a
    Fernet token but doesn't decrypt raises, because that means a wrong key.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return decrypt(value)
        except InvalidToken:
            if value.startswith(FERNET_PREFIX):
                raise
            return value  # legacy plaintext from before encryption at rest
