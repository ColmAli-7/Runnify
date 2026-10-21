"""progress of background jobs

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-21 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('garmin_sync_done', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('garmin_sync_total', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('garmin_sync_updated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('history_import_done', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('history_import_total', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('history_import_updated_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('history_import_updated_at')
        batch_op.drop_column('history_import_total')
        batch_op.drop_column('history_import_done')
        batch_op.drop_column('garmin_sync_updated_at')
        batch_op.drop_column('garmin_sync_total')
        batch_op.drop_column('garmin_sync_done')
