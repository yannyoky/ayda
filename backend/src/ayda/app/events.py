"""Local events (US-19, ADR 0008 and 0015): the nightly listings load, event quests for the
pool and the interest score that orders events for the pool and the assistant's search.

Code alone picks event quests: events in the user's city first, then elsewhere in their
region, starting at least an hour from now and before the quest day ends; among those the
ones closest to what the user wrote and to their goals go first.
"""

import random
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.config import Settings
from ayda.core.jobs import enqueue
from ayda.modules import auth, events, quests
from ayda.modules.quests.day_service import NewQuest

INGEST_JOB = "events.ingest"
VENUES_JOB = "events.venues"
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


# Event categories that serve each goal (codes from the habits goal catalog).
GOAL_CATEGORIES: dict[str, tuple[str, ...]] = {
    "more_movement": ("sport", "walk"),
    "less_screen": ("social", "city", "sport"),
    "see_friends": ("social",),
    "explore_city": ("city", "walk"),
    "learn": ("learning",),
    "own_project": ("learning",),
    "rest_well": ("city", "rest"),
    "calm_mind": ("walk", "rest"),
}
_WORD = re.compile(r"[а-яёa-z0-9-]{3,}")
# Words that say nothing about what kind of event the user wants.
_STOP = frozenset((
    "сегодня", "завтра", "вечер", "вечером", "утром", "днём", "днем", "выходные", "выходных",
    "неделе", "неделю", "хочу", "хочется", "куда", "сходить", "где", "какие", "какой", "какое",
    "что", "есть", "будет", "будут", "можно", "найди", "покажи", "подскажи", "интересное",
    "интересного", "интересные", "афиша", "афишу", "афише", "событие", "события", "событий",
    "мероприятие", "мероприятия", "мероприятий", "рядом", "городе", "области", "работа",
    "работаю", "дела", "дом", "дома", "после", "потом", "надо", "нужно", "ещё", "еще", "очень",
    "просто", "сделать", "хотел", "хотела",
))  # fmt: skip


def stems(text: str, limit: int = 8) -> tuple[str, ...]:
    """Word stems for matching titles: lower case, ё as е, endings cut, filler words out."""
    out: list[str] = []
    for word in _WORD.findall(text.lower().replace("ё", "е")):
        if word in _STOP or word.isdigit():
            continue
        stem = word[: max(4, len(word) - 2)]
        if stem not in out:
            out.append(stem)
    return tuple(out[:limit])


TASTE_DAYS = 60
TASTE_HALF_LIFE_DAYS = 30
TASTE_SATURATION = 4.0
TASTE_CATEGORY_POINTS = 2.0
TASTE_WORD_CAP = 2.0
# What one quest says about the user: finished is a strong yes, taken a weak yes, swapped
# away a no ("dont_want" is a clear one; "no_time" and "cant" say little about taste).
_SIGNAL_WEIGHT = {"completed": 3.0, "taken": 1.0}
_REJECT_WEIGHT = {"dont_want": -2.5, "no_time": -0.5, "cant": 0.0}


@dataclass(frozen=True)
class Taste:
    """A user's taste learned from what they took, finished and swapped away (ADR 0017):
    a share in (-1, 1) per quest category, and a weight per stem of event titles."""

    categories: dict[str, float] = field(default_factory=lambda: {})
    words: dict[str, float] = field(default_factory=lambda: {})


def learn_taste(signals: Iterable[quests.QuestSignal], today: date) -> Taste:
    """Sums the signals with a 30-day half-life; a few signs stay modest because the
    saturation keeps a share well under 1."""
    cats: dict[str, float] = {}
    words: dict[str, float] = {}
    for s in signals:
        weight = (
            _REJECT_WEIGHT.get(s.reject_reason or "", -0.5)
            if s.state == "replaced"
            else _SIGNAL_WEIGHT.get(s.state, 0.0)
        )
        if weight == 0.0:
            continue
        weight *= 0.5 ** (max((today - s.local_date).days, 0) / TASTE_HALF_LIFE_DAYS)
        cats[s.category] = cats.get(s.category, 0.0) + weight
        if s.source == "event":
            for stem in {w[:4] for w in stems(s.title, limit=6)}:  # short: джазовый ~ джаза
                words[stem] = words.get(stem, 0.0) + weight
    return Taste(
        categories={c: v / (abs(v) + TASTE_SATURATION) for c, v in cats.items()},
        words={w: v / (abs(v) + TASTE_SATURATION) for w, v in words.items()},
    )


async def load_taste(session: AsyncSession, user_id: uuid.UUID, today: date) -> Taste:
    since = today - timedelta(days=TASTE_DAYS)
    return learn_taste(await quests.recent_signals(session, user_id, since), today)


@dataclass(frozen=True)
class Interest:
    """What the user is into right now: words they asked for (strong), words of their
    check-in (weak), a category and their goals."""

    asked: tuple[str, ...] = ()
    mentioned: tuple[str, ...] = ()
    category: str | None = None
    goals: tuple[str, ...] = ()
    taste: Taste = field(default_factory=Taste)

    def categories(self) -> set[str]:
        return {c for g in self.goals for c in GOAL_CATEGORIES.get(g, ())}


def _hits(title: str, words: Iterable[str]) -> int:
    lowered = title.lower().replace("ё", "е")
    return sum(1 for w in words if w in lowered)


def interest_score(listing: events.Listing | events.ListingData, interest: Interest) -> float:
    """How well an event fits the user; place and time are weighed by the caller."""
    score = 3.0 * _hits(listing.title, interest.asked)
    score += min(_hits(listing.title, interest.mentioned), 3)
    if interest.category and listing.category == interest.category:
        score += 2
    if listing.category in interest.categories():
        score += 1
    if listing.is_free:
        score += 0.5
    score += TASTE_CATEGORY_POINTS * interest.taste.categories.get(listing.category, 0.0)
    lowered = listing.title.lower().replace("ё", "е")
    liked = sum(v for w, v in interest.taste.words.items() if w in lowered)
    return score + max(-TASTE_WORD_CAP, min(TASTE_WORD_CAP, TASTE_WORD_CAP * liked))


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


def venue_http() -> httpx.AsyncClient:
    """A city query to Overpass can take well over the 15 s of the listings' client."""
    return httpx.AsyncClient(timeout=120.0, headers={"User-Agent": USER_AGENT})


async def request_venue_load(session: AsyncSession, city_id: int, now: datetime) -> bool:
    """Queue a load now for a city that has none yet, instead of waiting for the night; once
    a day per city, and the job loads every city that is due."""
    day = now.date().isoformat()
    return await enqueue(
        session,
        VENUES_JOB,
        {"day": day, "city_id": city_id},
        dedupe_key=f"{VENUES_JOB}:asked:{city_id}:{day}",
        max_attempts=3,
    )


def venue_source(settings: Settings, http: httpx.AsyncClient) -> events.OverpassSource | None:
    urls = [u.strip() for u in settings.venues_overpass_urls.split(",") if u.strip()]
    return events.OverpassSource(http, urls) if urls else None


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


async def schedule_venues(session: AsyncSession, settings: Settings, now: datetime) -> bool:
    """Queue tonight's venue load once, like the listings; each run loads a few cities."""
    day = _due_date(settings, now)
    if day is None or not settings.venues_overpass_urls.strip():
        return False
    return await enqueue(
        session, VENUES_JOB, {"day": day}, dedupe_key=f"{VENUES_JOB}:{day}", max_attempts=3
    )


async def run_venues(
    session: AsyncSession, source: events.OverpassSource, radius_m: int, now: datetime
) -> dict[int, int]:
    city_ids = await auth.user_city_ids(session)
    return await events.load_venues(session, source, city_ids, radius_m, now)


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
    interest: Interest | None = None,
) -> list[NewQuest]:
    """Allowed events for today, one per title: the best fit for `interest` first, then by
    place (own city, then nearest) and time."""
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
    if interest is not None:
        allowed.sort(key=lambda x: -interest_score(x, interest))  # stable: keeps place order
    return await _as_quests(session, allowed, user.city_id)


def pick_for_pool(candidates: Sequence[NewQuest], seed: str) -> list[NewQuest]:
    """The best event, then one of the next 4; the second varies from day to day."""
    if not candidates:
        return []
    rest = list(candidates[1:5])
    rng = random.Random(seed)
    return [candidates[0], *rng.sample(rest, min(EVENTS_IN_POOL - 1, len(rest)))]


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
