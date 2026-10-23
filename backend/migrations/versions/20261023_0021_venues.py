"""events.venues and events.venue_loads: OpenStreetMap venues for meetups (M5, ADR 0011)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE events.venues (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            osm_type text NOT NULL CHECK (osm_type IN ('node', 'way', 'relation')),
            osm_id bigint NOT NULL,
            city_id integer NOT NULL REFERENCES events.cities (id),
            name text NOT NULL,
            kind text NOT NULL CHECK (kind IN ('restaurant', 'cafe', 'bar', 'pub', 'fast_food')),
            cuisine text,
            address text,
            location geography(Point, 4326) NOT NULL,
            opening_hours text,
            website text,
            loaded_at timestamptz NOT NULL,
            CONSTRAINT uq_venues_osm_type_osm_id UNIQUE (osm_type, osm_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_venues_city_id_kind ON events.venues (city_id, kind)")
    # When a city was last loaded, even if it returned nothing, so that it is not re-queried
    # every night.
    op.execute(
        """
        CREATE TABLE events.venue_loads (
            city_id integer PRIMARY KEY REFERENCES events.cities (id),
            loaded_at timestamptz NOT NULL,
            venues integer NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE events.venue_loads")
    op.execute("DROP TABLE events.venues")
