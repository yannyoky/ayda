"""events.venues: places for a walk next to the meetup venues (M6, ADR 0013)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOOD = "'restaurant', 'cafe', 'bar', 'pub', 'fast_food'"
WALK = "'park', 'garden', 'embankment', 'viewpoint', 'square'"


def upgrade() -> None:
    op.execute("ALTER TABLE events.venues DROP CONSTRAINT venues_kind_check")
    op.execute(
        "ALTER TABLE events.venues ADD CONSTRAINT venues_kind_check"
        f" CHECK (kind IN ({FOOD}, {WALK}))"
    )
    # Public map data only: forgetting the load dates makes the worker load every city again,
    # now with the places for a walk.
    op.execute("DELETE FROM events.venue_loads")


def downgrade() -> None:
    op.execute(f"DELETE FROM events.venues WHERE kind IN ({WALK})")
    op.execute("ALTER TABLE events.venues DROP CONSTRAINT venues_kind_check")
    op.execute(
        f"ALTER TABLE events.venues ADD CONSTRAINT venues_kind_check CHECK (kind IN ({FOOD}))"
    )
