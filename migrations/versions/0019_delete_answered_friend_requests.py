"""delete answered friend requests

Accepting a friend request now keeps only the friendship, and declining one
keeps nothing, so a request is deleted once it is answered. This removes the
accepted and declined requests stored before then. Nothing read them, and
they can't be brought back.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-02 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("DELETE FROM friend_requests WHERE status IS NULL OR status <> 'pending'"))


def downgrade():
    pass  # the answered requests are gone for good
