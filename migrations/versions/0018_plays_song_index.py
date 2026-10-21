"""index plays by song

Removing the songs no play uses any more (when an account is deleted) looks
each song up among the plays.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-22 10:30:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_song_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_song_history_song_id'), ['song_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_song_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_song_history_song_id'))
