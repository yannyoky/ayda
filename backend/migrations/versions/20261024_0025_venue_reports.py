"""events.venue_reports: "Не работает" marks from users on venues

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # OpenStreetMap has opening hours but not "closed for a while"; users fill the gap.
    op.execute(
        """
        CREATE TABLE events.venue_reports (
            venue_id bigint NOT NULL REFERENCES events.venues (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            reported_at timestamptz NOT NULL,
            PRIMARY KEY (venue_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_venue_reports_reported_at ON events.venue_reports (reported_at)")


def downgrade() -> None:
    op.execute("DROP TABLE events.venue_reports")
