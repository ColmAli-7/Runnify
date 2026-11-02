"""Encryption at rest for third-party credentials.

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256). ``FERNET_KEYS``
may list several comma-separated keys, newest first: new values are encrypted
with the first key and old values still decrypt with any of them, which allows
rotating keys without downtime. ``FERNET_KEY`` alone works too. Before an old
key is removed, :func:`reencrypt_stored` (``flask --app runnify secrets
reencrypt``) re-saves every stored value under the newest one, since values
are otherwise only re-encrypted when something happens to save them again.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app
from sqlalchemy import bindparam, select, update
from sqlalchemy import column as sa_column
from sqlalchemy import table as sa_table
from sqlalchemy.types import String, TypeDecorator

from runnify.extensions import db

FERNET_PREFIX = "gAAAAA"  # every Fernet token starts with the version byte and timestamp


def _ciphers():
    """One Fernet cipher a configured key, newest first (``FERNET_KEYS``, else ``FERNET_KEY``)."""
    config = current_app.config
    keys = [k.strip() for k in (config.get("FERNET_KEYS") or "").split(",") if k.strip()]
    if not keys and config.get("FERNET_KEY"):
        keys = [config["FERNET_KEY"]]
    if not keys:
        raise RuntimeError("FERNET_KEY is not configured; it is needed to store credentials")
    return [Fernet(key.encode()) for key in keys]


def fernet():
    """Return the app's (multi-)Fernet cipher built from ``FERNET_KEYS`` / ``FERNET_KEY``."""
    return MultiFernet(_ciphers())


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


def _opens(cipher, token):
    """Whether ``cipher`` decrypts ``token``."""
    try:
        cipher.decrypt(token)
    except InvalidToken:
        return False
    return True


def _resaved(value, keys, newest):
    """``value`` as stored under the ``newest`` key, or ``None`` when it already is.

    Raises :class:`InvalidToken` for a Fernet token that no key decrypts, as
    :class:`EncryptedString` does; anything else is legacy plaintext.
    """
    token = value.encode()
    if _opens(newest, token):
        return None
    if _opens(keys, token):
        return keys.rotate(token).decode()
    if value.startswith(FERNET_PREFIX):
        raise InvalidToken
    return newest.encrypt(token).decode()


def reencrypt_stored(batch=500):
    """Re-save every :class:`EncryptedString` value under the newest key (the caller commits).

    Returns ``(resaved, unreadable)``: how many values were rewritten, and a
    ``("table.column", primary key)`` pair for each that no configured key
    decrypts, which is left as it is. Values already under the newest key are
    left alone and legacy plaintext is encrypted, so running it twice is safe.
    """
    ciphers = _ciphers()
    keys, newest = MultiFernet(ciphers), ciphers[0]
    resaved, unreadable = 0, []
    encrypted = [
        (table, column)
        for table in db.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, EncryptedString)
    ]
    for table, column in encrypted:
        (key,) = table.primary_key.columns
        stored = sa_table(table.name, sa_column(key.name), sa_column(column.name))  # untyped: raw
        updates = []
        for row, value in db.session.execute(
            select(stored.c[key.name], stored.c[column.name]).where(
                stored.c[column.name].isnot(None)
            )
        ):
            try:
                token = _resaved(value, keys, newest)
            except InvalidToken:
                unreadable.append((f"{table.name}.{column.name}", row))
                continue
            if token is not None:
                updates.append({"row": row, "token": token})
        for start in range(0, len(updates), batch):
            db.session.execute(
                update(stored)
                .where(stored.c[key.name] == bindparam("row"))
                .values({column.name: bindparam("token")}),
                updates[start : start + batch],
            )
        resaved += len(updates)
    return resaved, unreadable
