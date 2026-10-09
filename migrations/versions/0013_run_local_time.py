"""run local time

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('utc_offset', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('runs', schema=None) as batch_op:
        batch_op.drop_column('utc_offset')
