"""events.listings and event quests in quests.day_quests (M3, US-19, ADR 0008)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "('sport', 'walk', 'city', 'rest', 'project', 'social', 'home', 'learning')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE events.listings (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source text NOT NULL CHECK (source IN ('timepad', 'kudago', 'culture')),
            source_id text NOT NULL,
            title text NOT NULL,
            starts_at timestamptz NOT NULL,
            ends_at timestamptz,
            venue text,
            address text,
            location geography(Point, 4326),
            city_id integer NOT NULL REFERENCES events.cities (id),
            region_code text NOT NULL,
            is_free boolean NOT NULL,
            price_min integer CHECK (price_min >= 0),
            url text NOT NULL,
            category text NOT NULL CHECK (category IN {CATEGORY}),
            fetched_at timestamptz NOT NULL,
            CONSTRAINT uq_listings_source_source_id UNIQUE (source, source_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_listings_region_code_starts_at ON events.listings (region_code, starts_at)"
    )
    op.execute("CREATE INDEX ix_listings_starts_at ON events.listings (starts_at)")

    op.execute("ALTER TABLE quests.day_quests DROP CONSTRAINT day_quests_source_check")
    op.execute(
        "ALTER TABLE quests.day_quests ADD CONSTRAINT day_quests_source_check"
        " CHECK (source IN ('catalog', 'checkin_task', 'custom', 'coop', 'event'))"
    )
    # The listing id (no foreign key across modules) and a snapshot of what the user saw.
    op.execute("ALTER TABLE quests.day_quests ADD COLUMN event_id bigint")
    op.execute("ALTER TABLE quests.day_quests ADD COLUMN event jsonb")
    op.execute(
        "ALTER TABLE quests.day_quests ADD CONSTRAINT day_quests_event_check"
        " CHECK ((source = 'event') = (event_id IS NOT NULL AND event IS NOT NULL))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE quests.day_quests DROP CONSTRAINT day_quests_event_check")
    # Event quests stay as own quests, so points and posts keep their quest.
    op.execute("UPDATE quests.day_quests SET source = 'custom' WHERE source = 'event'")
    op.execute("ALTER TABLE quests.day_quests DROP COLUMN event")
    op.execute("ALTER TABLE quests.day_quests DROP COLUMN event_id")
    op.execute("ALTER TABLE quests.day_quests DROP CONSTRAINT day_quests_source_check")
    op.execute(
        "ALTER TABLE quests.day_quests ADD CONSTRAINT day_quests_source_check"
        " CHECK (source IN ('catalog', 'checkin_task', 'custom', 'coop'))"
    )
    op.execute("DROP TABLE events.listings")
