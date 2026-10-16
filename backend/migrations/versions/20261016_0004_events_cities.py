"""events.cities: city reference data with PostGIS location

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from ayda.modules.events.cities import load_city_rows

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE events.cities (
            id integer PRIMARY KEY,
            name text NOT NULL,
            region_code text NOT NULL,
            region_name text NOT NULL,
            timezone text NOT NULL,
            location geography(Point, 4326) NOT NULL,
            population integer NOT NULL
        )
        """
    )
    rows = [
        {
            "id": int(r["id"]),
            "name": r["name"],
            "region_code": r["region_code"],
            "region_name": r["region_name"],
            "timezone": r["timezone"],
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "population": int(r["population"]),
        }
        for r in load_city_rows()
    ]
    op.get_bind().execute(
        sa.text(
            "INSERT INTO events.cities"
            " (id, name, region_code, region_name, timezone, location, population)"
            " VALUES (:id, :name, :region_code, :region_name, :timezone,"
            " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :population)"
        ),
        rows,
    )
    op.execute("CREATE INDEX ix_cities_location ON events.cities USING gist (location)")
    op.execute("CREATE INDEX ix_cities_region_code ON events.cities (region_code)")


def downgrade() -> None:
    op.execute("DROP TABLE events.cities")
