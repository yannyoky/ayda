"""The "top nearby" picks (ADR 0016): the most notable events of the user's region in the next
two weeks, chosen without the user's tastes. Prominence comes from what a listing itself says
(a public place, free entry, a long or repeated run, a mass-event word) and from a calendar of
seasonal holidays, so events nobody listed in advance (a battle reenactment on 9 May) still
rise when their season comes. Code decides everything; no LLM is involved."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import AssistantEvent
from ayda.app.assistant_chat import event_card
from ayda.modules import auth, events

HORIZON = timedelta(days=14)
TOP_SHOWN = 6
POOL = 300

_PUBLIC_PLACE = (
    "площадь", "парк", "набережн", "форт", "стадион", "пляж", "сквер", "аллея", "крепост",
    "замок", "улиц", "променад", "остров", "маяк", "порт", "кирха", "бастион",
)  # fmt: skip
# Words of events that gather a crowd; a hint, not a list of allowed events.
_CROWD = (
    "фестивал", "ярмарк", "праздник", "день города", "открыт", "парад", "салют", "реконструкц",
    "шествие", "марафон", "забег", "ночь", "гуляни", "карнавал", "фейерверк", "массов",
    "всей семь", "день ", "масленица", "open air", "опен эйр",
)  # fmt: skip


@dataclass(frozen=True)
class Season:
    """A recurring holiday window (month/day, inclusive) and the words its events carry."""

    name: str
    start: tuple[int, int]
    end: tuple[int, int]
    words: tuple[str, ...]


# Fixed-date and roughly dated holidays; movable ones get a wide window. Extend as needed.
SEASONS = (
    Season(
        "new_year",
        (12, 20),
        (1, 8),
        ("новогод", "новый год", "ёлк", "елк", "рождеств", "снегурочк"),
    ),
    Season("defender", (2, 17), (2, 23), ("защитник", "23 февраля", "армии", "военн")),
    Season("maslenitsa", (2, 10), (3, 20), ("масленица", "масленич")),
    Season("women", (3, 3), (3, 8), ("8 марта", "женск", "весна")),
    Season("easter", (4, 1), (5, 5), ("пасх", "светлой")),
    Season(
        "may",
        (4, 28),
        (5, 9),
        (
            "победы",
            "победа",
            "9 мая",
            "ветеран",
            "бессмертн",
            "георгиев",
            "форт",
            "реконструкц",
            "парад",
            "салют",
            "1 мая",
            "майск",
        ),
    ),
    Season("russia_day", (6, 8), (6, 12), ("день россии", "россии")),
    Season("navy", (7, 20), (7, 31), ("вмф", "флот", "корабл", "морск", "парусн", "яхт")),
    Season("knowledge", (8, 25), (9, 3), ("день знаний", "первый звонок", "школ")),
    Season("unity", (10, 30), (11, 4), ("единств", "4 ноября")),
    Season("halloween", (10, 25), (10, 31), ("хэллоуин", "хеллоуин", "halloween")),
)


def _in_window(day: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    here = (day.month, day.day)
    if start <= end:
        return start <= here <= end
    return here >= start or here <= end


def active_seasons(day: date) -> list[Season]:
    """Seasons whose window covers `day`, or starts within the next 14 days."""
    soon = day + HORIZON
    return [
        s for s in SEASONS if _in_window(day, s.start, s.end) or _in_window(soon, s.start, s.end)
    ]


def _title_key(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower().replace("ё", "е")).strip()


def prominence(
    listing: events.Listing | events.ListingData,
    repeats: int,
    seasons: list[Season],
    at_home: bool,
    distance_m: int,
) -> float:
    """How notable an event is on its own, with no user tastes involved."""
    lowered = listing.title.lower().replace("ё", "е")
    place = f"{listing.venue or ''} {listing.address or ''}".lower()
    score = 0.0
    if any(w in place for w in _PUBLIC_PLACE):
        score += 2
    if listing.is_free:
        score += 1.5
    elif listing.price_min and listing.price_min > 3000:
        score -= 1
    if any(w in lowered for w in _CROWD):
        score += 2
    score += min(repeats - 1, 2)  # a series or several days is a festival, not a one-off
    if listing.ends_at and listing.ends_at - listing.starts_at >= timedelta(hours=4):
        score += 1
    if any(w in lowered or w in place for s in seasons for w in s.words):
        score += 4
    score += 1 if at_home else -min(distance_m / 100_000, 1.5)
    return score


async def top_nearby(
    session: AsyncSession, user: auth.User, now: datetime, limit: int = TOP_SHOWN
) -> list[AssistantEvent]:
    """The region's most notable events of the next two weeks, one per title, best first."""
    if user.city_id is None:
        return []
    hits = await events.region_events(session, user.city_id, now, now + HORIZON, POOL)
    if not hits:
        return []
    day = now.astimezone(ZoneInfo(user.timezone)).date()
    seasons = active_seasons(day)
    runs = Counter(_title_key(h.listing.title) for h in hits)
    ranked = sorted(
        hits,
        key=lambda h: (
            -prominence(
                h.listing,
                runs[_title_key(h.listing.title)],
                seasons,
                h.listing.city_id == user.city_id,
                h.distance_m,
            ),
            h.listing.starts_at,
            h.listing.id,
        ),
    )
    seen: set[str] = set()
    shown: list[AssistantEvent] = []
    for hit in ranked:
        key = _title_key(hit.listing.title)
        if key in seen:
            continue
        seen.add(key)
        shown.append(event_card(hit))
        if len(shown) == limit:
            break
    return shown
