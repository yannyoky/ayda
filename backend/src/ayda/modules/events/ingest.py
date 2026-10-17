"""The nightly load of event listings from every source for the cities that have users."""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.events.listings import purge_listings, save_listings
from ayda.modules.events.sources import CityRef, EventSource

log = logging.getLogger(__name__)

WINDOW = timedelta(days=3)


async def ingest(
    session: AsyncSession, sources: Sequence[EventSource], cities: Sequence[CityRef], now: datetime
) -> dict[str, int]:
    """Load the next 3 days of events; a failing source or city does not stop the others.
    Returns the number of listings saved per source; logs counts only."""
    saved = dict.fromkeys((s.name for s in sources), 0)
    failed = dict.fromkeys((s.name for s in sources), 0)
    for city in cities:
        for source in sources:
            if not source.supports(city):
                continue
            try:
                items = await source.fetch(city, now, now + WINDOW)
            except (httpx.HTTPError, ValueError) as exc:
                failed[source.name] += 1
                log.warning("events: %s failed for a city: %s", source.name, type(exc).__name__)
                continue
            saved[source.name] += await save_listings(session, items, now)
    purged = await purge_listings(session, now)
    log.info(
        "events: loaded %s for %d cities, %d sources failed, %d old purged",
        saved,
        len(cities),
        sum(failed.values()),
        purged,
    )
    return saved
