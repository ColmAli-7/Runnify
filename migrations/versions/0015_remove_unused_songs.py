"""remove songs that no play or playlist uses

The history import used to add every track in an upload to the song
catalogue, though only plays during runs were kept. It now only adds songs
that played during a run; this removes the rest. The songs in use are
gathered first and the others deleted by id, which stays quick on SQLite and
PostgreSQL alike however large the tables are.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-21 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    used = {
        song_id
        for (song_id,) in connection.execute(
            sa.text("SELECT DISTINCT song_id FROM user_song_history WHERE song_id IS NOT NULL")
        )
    }
    used.update(song_id for (song_id,) in connection.execute(sa.text("SELECT DISTINCT song_id FROM playlist_tracks")))
    unused = [song_id for (song_id,) in connection.execute(sa.text("SELECT id FROM songs")) if song_id not in used]
    delete = sa.text("DELETE FROM songs WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True))
    for start in range(0, len(unused), 500):
        connection.execute(delete, {"ids": unused[start : start + 500]})


def downgrade():
    pass  # the removed songs come back with the next upload that plays them during a run
