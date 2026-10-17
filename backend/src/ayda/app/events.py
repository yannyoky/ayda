"""Local events (US-19, ADR 0008): the nightly listings load and event quests for the pool.

Code alone picks event quests: events in the user's city first, then elsewhere in their
region, starting at least an hour from now and before the quest day ends.
"""

import random
from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.config import Settings
from ayda.core.jobs import enqueue
from ayda.modules import auth, events, quests
from ayda.modules.quests.day_service import NewQuest

INGEST_JOB = "events.ingest"
EVENTS_IN_POOL = 2
EVENT_CANDIDATES = 20
MIN_LEAD = timedelta(hours=1)
MIN_DURATION = 60
MAX_DURATION = 240
DEFAULT_DURATION = 120
MAX_TITLE = 140
USER_AGENT = "Ayda/0.3 (Telegram Mini App; events once a day)"

WHY_FREE = "Бесплатно и сегодня: хороший повод выбраться."
WHY_HOME = "Событие сегодня в твоём городе."


def default_sources(settings: Settings, http: httpx.AsyncClient) -> list[events.EventSource]:
    token = settings.timepad_token.get_secret_value() if settings.timepad_token else None
    known: dict[str, events.EventSource] = {
        "timepad": events.TimepadSource(http, token),
        "kudago": events.KudaGoSource(http),
    }
    names = [n.strip() for n in settings.events_sources.split(",") if n.strip()]
    return [known[n] for n in names if n in known]


def source_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT})


def _due_date(settings: Settings, now: datetime) -> str | None:
    local = now.astimezone(ZoneInfo(settings.events_timezone))
    if local.time() < settings.events_ingest_at:
        return None
    return local.date().isoformat()


async def schedule_ingest(session: AsyncSession, settings: Settings, now: datetime) -> bool:
    """Queue today's load once (dedupe key per local date); the job retries on failure."""
    day = _due_date(settings, now)
    if day is None or not settings.events_sources.strip():
        return False
    return await enqueue(
        session, INGEST_JOB, {"day": day}, dedupe_key=f"{INGEST_JOB}:{day}", max_attempts=3
    )


async def run_ingest(
    session: AsyncSession, sources: Sequence[events.EventSource], now: datetime
) -> dict[str, int]:
    cities = await events.cities_to_load(session, await auth.user_city_ids(session))
    return await events.ingest(session, sources, cities, now)


# --- event quests -------------------------------------------------------------------------


def duration_min(listing: events.Listing) -> int:
    if listing.ends_at is None:
        return DEFAULT_DURATION
    minutes = int((listing.ends_at - listing.starts_at).total_seconds() // 60)
    return max(MIN_DURATION, min(minutes, MAX_DURATION))


def event_quest(listing: events.Listing, home_city_id: int, city_name: str | None) -> NewQuest:
    other_city = listing.city_id != home_city_id
    if listing.is_free:
        why = WHY_FREE
    elif other_city and city_name:
        why = f"Стоит съездить: {city_name}."
    else:
        why = WHY_HOME
    title = (
        listing.title if len(listing.title) <= MAX_TITLE else listing.title[: MAX_TITLE - 1] + "…"
    )
    return NewQuest(
        source="event",
        title=title,
        category=listing.category,
        duration_min=duration_min(listing),
        why=why,
        event_id=listing.id,
        event={
            "title": listing.title,
            "starts_at": listing.starts_at.isoformat(),
            "ends_at": listing.ends_at.isoformat() if listing.ends_at else None,
            "venue": listing.venue,
            "address": listing.address,
            "city": city_name if other_city else None,
            "is_free": listing.is_free,
            "price_min": listing.price_min,
            "url": listing.url,
            "source": listing.source,
        },
    )


async def _as_quests(
    session: AsyncSession, listings: Sequence[events.Listing], home_city_id: int
) -> list[NewQuest]:
    names = await events.get_cities(session, sorted({x.city_id for x in listings}))
    return [
        event_quest(x, home_city_id, names[x.city_id].name if x.city_id in names else None)
        for x in listings
    ]


async def event_candidates(
    session: AsyncSession,
    user: auth.User,
    day_ends_at: datetime,
    max_duration: int,
    exclude: set[int],
    now: datetime,
) -> list[NewQuest]:
    """Allowed events for today, best first, one per title."""
    if user.city_id is None:
        return []
    listings = await events.upcoming_near(
        session, user.city_id, now + MIN_LEAD, day_ends_at, EVENT_CANDIDATES
    )
    seen: set[str] = set()
    allowed: list[events.Listing] = []
    for listing in listings:
        key = listing.title.casefold()
        if listing.id in exclude or key in seen or duration_min(listing) > max_duration:
            continue
        seen.add(key)
        allowed.append(listing)
    return await _as_quests(session, allowed, user.city_id)


def pick_for_pool(candidates: Sequence[NewQuest], seed: str) -> list[NewQuest]:
    """Up to 2 events from the best 6, in their order; varies from day to day."""
    top = list(candidates[:6])
    rng = random.Random(seed)
    chosen = sorted(rng.sample(range(len(top)), min(EVENTS_IN_POOL, len(top))))
    return [top[i] for i in chosen]


def event_picker(session: AsyncSession, user: auth.User, now: datetime) -> quests.EventPicker:
    """For replacing an event quest: the next of the day's event candidates still ahead."""

    async def pick(pool: quests.DayPool, skip: set[int]) -> NewQuest | None:
        if user.city_id is None:
            return None
        ids = [int(i) for i in pool.context.get("event_ids", []) if int(i) not in skip]
        by_id = await events.get_listings(session, ids)
        for i in ids:
            listing = by_id.get(i)
            if listing is not None and listing.starts_at >= now + MIN_LEAD:
                return (await _as_quests(session, [listing], user.city_id))[0]
        return None

    return pick
