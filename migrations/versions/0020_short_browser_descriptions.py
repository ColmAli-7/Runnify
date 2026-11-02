"""keep only a short description of each security event's browser

The security log kept each browser's user agent, cut at 160 characters,
which is the whole header for most browsers. It now keeps only the short
description Settings shows, such as "Chrome on Windows", and this shortens
the user agents already stored. The full ones can't be brought back.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-02 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

from runnify.security.audit import describe_browser


# revision identifiers, used by Alembic.
revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

events = sa.table(
    "security_events", sa.column("id", sa.Integer), sa.column("user_agent", sa.String)
)


def upgrade():
    connection = op.get_bind()
    stored = connection.execute(  # a user agent always has a "/", a description never does
        sa.select(events.c.id, events.c.user_agent).where(events.c.user_agent.like("%/%"))
    ).all()
    for event_id, agent in stored:
        connection.execute(
            events.update()
            .where(events.c.id == event_id)
            .values(user_agent=describe_browser(agent))
        )


def downgrade():
    pass  # the full user agents are gone for good
