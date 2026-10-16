import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.events.models import City

CITIES_CSV = Path(__file__).parent / "data" / "cities.csv"


@dataclass(frozen=True)
class CityPoint:
    """City center, used for weather; never a user's own location."""

    lat: float
    lon: float


def load_city_rows() -> list[dict[str, str]]:
    with CITIES_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


async def get_city(session: AsyncSession, city_id: int) -> City | None:
    return await session.get(City, city_id)


async def get_cities(session: AsyncSession, city_ids: list[int]) -> dict[int, City]:
    if not city_ids:
        return {}
    rows = await session.execute(select(City).where(City.id.in_(city_ids)))
    return {c.id: c for c in rows.scalars()}


async def search_cities(session: AsyncSession, query: str, limit: int) -> list[City]:
    """Name prefix matches first, then substring matches; bigger cities first."""
    q = query.strip().lower().replace("ё", "е")
    name = func.replace(func.lower(City.name), "ё", "е")
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    prefix_first = (name.like(q.replace("%", "") + "%")).desc()
    stmt = (
        select(City)
        .where(name.like(pattern))
        .order_by(prefix_first, City.population.desc(), City.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def nearest_cities(session: AsyncSession, lat: float, lon: float, limit: int) -> list[City]:
    """Cities closest to a point. The point is used for this query only and never stored."""
    ids = await session.execute(
        text(
            "SELECT id FROM events.cities"
            " ORDER BY location <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography"
            " LIMIT :limit"
        ),
        {"lat": lat, "lon": lon, "limit": limit},
    )
    ordered = [row[0] for row in ids]
    by_id = await get_cities(session, ordered)
    return [by_id[i] for i in ordered]


async def city_point(session: AsyncSession, city_id: int) -> CityPoint | None:
    row = (
        await session.execute(
            text(
                "SELECT ST_Y(location::geometry), ST_X(location::geometry)"
                " FROM events.cities WHERE id = :id"
            ),
            {"id": city_id},
        )
    ).first()
    return CityPoint(lat=float(row[0]), lon=float(row[1])) if row else None
