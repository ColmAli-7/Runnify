"""encrypt spotify tokens

Spotify access and refresh tokens used to be stored in plain text; the model
now encrypts them (EncryptedString). This encrypts any existing plain-text
tokens in place. Garmin passwords were already encrypted with the same key.
Requires FERNET_KEY (or FERNET_KEYS) when there are tokens to encrypt.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09 19:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from runnify.security.crypto import FERNET_PREFIX, decrypt, encrypt

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

COLUMNS = ("spotify_token", "spotify_refresh_token")
users = sa.table("users", sa.column("id", sa.Integer), *(sa.column(c, sa.String) for c in COLUMNS))


def _rewrite(transform, needs_change):
    connection = op.get_bind()
    for row in connection.execute(sa.select(users.c.id, *(users.c[c] for c in COLUMNS))).all():
        values = {c: transform(v) for c, v in zip(COLUMNS, row[1:], strict=True) if v and needs_change(v)}
        if values:
            connection.execute(users.update().where(users.c.id == row[0]).values(**values))


def upgrade():
    _rewrite(encrypt, lambda value: not value.startswith(FERNET_PREFIX))


def downgrade():
    _rewrite(decrypt, lambda value: value.startswith(FERNET_PREFIX))
