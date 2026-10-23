"""Event listings: storing what the sources return and finding events near a user's city."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.events.models import City, Listing
from ayda.modules.events.sources import CityRef, ListingData

KEEP_ENDED = timedelta(days=2)
# Towns of a region loaded besides the users' own cities, biggest first (ADR 0015).
REGION_TOWNS = 15

_UPSERT = text(
    """
    INSERT INTO events.listings (
        source, source_id, title, starts_at, ends_at, venue, address, location,
        city_id, region_code, is_free, price_min, url, category, fetched_at
    ) VALUES (
        :source, :source_id, :title, :starts_at, :ends_at, :venue, :address,
        CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL
             ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography END,
        :city_id, :region_code, :is_free, :price_min, :url, :category, :fetched_at
    )
    ON CONFLICT (source, source_id) DO UPDATE SET
        title = EXCLUDED.title, starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at,
        venue = EXCLUDED.venue, address = EXCLUDED.address, location = EXCLUDED.location,
        city_id = EXCLUDED.city_id, region_code = EXCLUDED.region_code,
        is_free = EXCLUDED.is_free, price_min = EXCLUDED.price_min, url = EXCLUDED.url,
        category = EXCLUDED.category, fetched_at = EXCLUDED.fetched_at
    """
)


async def save_listings(session: AsyncSession, items: Sequence[ListingData], now: datetime) -> int:
    """Insert or refresh listings by (source, source_id)."""
    if not items:
        return 0
    unique = {(i.source, i.source_id): i for i in items}
    await session.execute(
        _UPSERT,
        [
            {
                "source": i.source,
                "source_id": i.source_id,
                "title": i.title,
                "starts_at": i.starts_at,
                "ends_at": i.ends_at,
                "venue": i.venue,
                "address": i.address,
                "lat": i.lat if i.lon is not None else None,
                "lon": i.lon if i.lat is not None else None,
                "city_id": i.city_id,
                "region_code": i.region_code,
                "is_free": i.is_free,
                "price_min": i.price_min,
                "url": i.url,
                "category": i.category,
                "fetched_at": now,
            }
            for i in unique.values()
        ],
    )
    return len(unique)


async def purge_listings(session: AsyncSession, now: datetime) -> int:
    """Drop listings that ended (or started, when the end is unknown) over 2 days ago."""
    cutoff = now - KEEP_ENDED
    deleted = await session.scalars(
        delete(Listing)
        .where(
            (Listing.ends_at < cutoff) | (Listing.ends_at.is_(None) & (Listing.starts_at < cutoff))
        )
        .returning(Listing.id)
    )
    return len(deleted.all())


async def cities_to_load(session: AsyncSession, city_ids: Sequence[int]) -> list[CityRef]:
    """The given cities plus the biggest towns of each of their regions (ADR 0015)."""
    if not city_ids:
        return []
    own = list(await session.scalars(select(City).where(City.id.in_(city_ids))))
    regions = sorted({c.region_code for c in own})
    rank = (
        func.row_number()
        .over(partition_by=City.region_code, order_by=(City.population.desc(), City.id))
        .label("rank")
    )
    ranked = select(City.id, rank).where(City.region_code.in_(regions)).subquery()
    towns = await session.scalars(
        select(City).join(ranked, ranked.c.id == City.id).where(ranked.c.rank <= REGION_TOWNS)
    )
    by_id = {c.id: c for c in [*own, *towns]}
    return [
        CityRef(c.id, c.name, c.region_code) for c in sorted(by_id.values(), key=lambda c: c.id)
    ]


async def upcoming_near(
    session: AsyncSession, city_id: int, since: datetime, until: datetime, limit: int = 20
) -> list[Listing]:
    """Events starting in [since, until] in the city, then elsewhere in its region by distance
    from the city center."""
    rows = await session.execute(
        text(
            """
            SELECT l.id FROM events.listings l
            JOIN events.cities home ON home.id = :city_id
            JOIN events.cities c ON c.id = l.city_id
            WHERE l.region_code = home.region_code
              AND l.starts_at BETWEEN :since AND :until
            ORDER BY l.city_id <> :city_id,
                     CASE WHEN l.city_id = :city_id THEN 0
                          ELSE ST_Distance(COALESCE(l.location, c.location), home.location) END,
                     l.starts_at, l.id
            LIMIT :limit
            """
        ),
        {"city_id": city_id, "since": since, "until": until, "limit": limit},
    )
    ordered = [r[0] for r in rows]
    by_id = await get_listings(session, ordered)
    return [by_id[i] for i in ordered]


@dataclass(frozen=True)
class RegionEvent:
    listing: Listing
    city_name: str
    distance_m: int


async def region_events(
    session: AsyncSession, city_id: int, since: datetime, until: datetime, limit: int = 200
) -> list[RegionEvent]:
    """Events starting in [since, until] anywhere in the city's region, soonest first, with
    the distance from the city's center; the caller ranks them."""
    rows = (
        await session.execute(
            text(
                """
                SELECT l.id, c.name,
                       CAST(ST_Distance(COALESCE(l.location, c.location), home.location) AS int)
                FROM events.listings l
                JOIN events.cities home ON home.id = :city_id
                JOIN events.cities c ON c.id = l.city_id
                WHERE l.region_code = home.region_code
                  AND l.starts_at BETWEEN :since AND :until
                ORDER BY l.starts_at, l.id
                LIMIT :limit
                """
            ),
            {"city_id": city_id, "since": since, "until": until, "limit": limit},
        )
    ).all()
    by_id = await get_listings(session, [r[0] for r in rows])
    return [RegionEvent(by_id[i], name, distance or 0) for i, name, distance in rows]


async def get_listings(session: AsyncSession, ids: Sequence[int]) -> dict[int, Listing]:
    if not ids:
        return {}
    rows = await session.scalars(select(Listing).where(Listing.id.in_(ids)))
    return {r.id: r for r in rows}
