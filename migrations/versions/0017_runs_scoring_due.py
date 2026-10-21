"""runs whose songs wait to be scored

Plays are stored before their runs are scored, so an import that stops in
between left runs unscored for good. A run now says when its songs wait to
be scored; runs that have plays but no scores at all wait from the start.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scoring_due', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(
        sa.text(
            "UPDATE runs SET scoring_due = :due"
            " WHERE id IN (SELECT DISTINCT run_id FROM user_song_history WHERE run_id IS NOT NULL)"
            " AND id NOT IN (SELECT DISTINCT run_id FROM run_song_analysis WHERE run_id IS NOT NULL)"
        ).bindparams(due=True)
    )


def downgrade():
    with op.batch_alter_table('runs', schema=None) as batch_op:
        batch_op.drop_column('scoring_due')
