"""remove songs that no play or playlist uses

The history import used to add every track in an upload to the song
catalogue, though only plays during runs were kept. It now only adds songs
that played during a run; this removes the rest.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-21 16:20:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "DELETE FROM songs"
        " WHERE id NOT IN (SELECT song_id FROM user_song_history WHERE song_id IS NOT NULL)"
        " AND id NOT IN (SELECT song_id FROM playlist_tracks)"
    )


def downgrade():
    pass  # the removed songs come back with the next upload that plays them during a run
