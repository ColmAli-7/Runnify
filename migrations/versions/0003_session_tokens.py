"""session tokens

Adds users.session_token, which is embedded in every session and remember-me
cookie so that rotating it signs a user out everywhere. Existing accounts get
their own random token; every session issued before this migration becomes
invalid, so users sign in once more after deploying it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09 18:30:00.000000

"""

import secrets

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("session_token", sa.String(length=64), nullable=True))

    users = sa.table("users", sa.column("id", sa.Integer), sa.column("session_token", sa.String))
    connection = op.get_bind()
    for (user_id,) in connection.execute(sa.select(users.c.id)).all():
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(session_token=secrets.token_urlsafe(32))
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("session_token", existing_type=sa.String(length=64), nullable=False)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("session_token")
