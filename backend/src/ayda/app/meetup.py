"""«Айда, организуй» (M5, US-17 + ADR 0010/0011): a meetup arranged from a chat.

On an explicit tap the last few messages of that chat go to the assistant, which only says
what kind of meetup it is, which kinds of venue fit and at what time. Code picks the 3-5
venues and builds the card; picking one creates a co-op with the venue as its place. The
chat is never read in the background, and its text is not logged or stored.
"""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import Coop, CoopCreateInput, MeetupOffer, MeetupPick, MeetupVenue, Place
from ayda.app import chat as chat_app
from ayda.app import coop as coop_app
from ayda.app.day import DayTools
from ayda.core.problems import Problem
from ayda.core.realtime import Realtime
from ayda.modules import analytics, assistant, auth, chat, events
from ayda.modules.analytics import EventType
from ayda.modules.quests import days as day_clock

log = logging.getLogger(__name__)

MESSAGES_READ = 8
MESSAGE_CHARS = 300
VENUES_SHOWN = 5
LEAD = timedelta(minutes=30)
ROUND_TO = 15
DEFAULT_TIME = time(19, 0)
DEFAULT_KINDS = ("cafe", "restaurant", "pub")
DEFAULT_DURATION = 90
LLM_DEADLINE_S = 12.0
MAX_FRIENDS = 3

NOTE_TOO_LATE = "На сегодня уже поздно: план живёт до конца дня. Попробуйте завтра."
NOTE_UNCLEAR = "Не поняла, о какой встрече речь. Напишите, где и когда хотите увидеться."
NOTE_NO_CITY = "Укажи город в профиле, и я подберу места рядом."
NOTE_NO_VENUES = "В вашем городе в карте пока мало подходящих мест. Выберите место сами."


def meetup_time(wanted: str | None, now: datetime, timezone: str) -> datetime | None:
    """Today's start time: the asked one, or 19:00, but not sooner than half an hour from now
    (rounded up to 15 minutes) and not after the day ends. None when it is too late."""
    local_now = day_clock.local_now(now, timezone)
    day = day_clock.local_day(now, timezone)
    hour, minute = map(int, wanted.split(":")) if wanted else (DEFAULT_TIME.hour, 0)
    start = datetime.combine(
        day if hour >= day_clock.DAY_STARTS_AT.hour else day + timedelta(days=1),
        time(hour, minute),
        ZoneInfo(timezone),
    )
    earliest = local_now + LEAD
    earliest += timedelta(minutes=-earliest.minute % ROUND_TO, seconds=-earliest.second)
    start = max(start, earliest.replace(microsecond=0))
    if start.astimezone(UTC) >= day_clock.day_expires_at(day, timezone) - LEAD:
        return None
    return start.astimezone(UTC)


def _venue(c: events.Candidate, city_name: str) -> MeetupVenue:
    links = events.map_links(c.venue.name, city_name)
    return MeetupVenue(
        id=c.venue.id,
        name=c.venue.name,
        kind=c.venue.kind,  # pyright: ignore[reportArgumentType]
        address=c.venue.address,
        distance_m=c.distance_m,
        opening_hours=c.venue.opening_hours,
        open_now=c.open_now,
        osm_url=events.osm_url(c.venue),
        gis_url=links["2gis"],
        yandex_url=links["yandex"],
    )


async def suggest(
    session: AsyncSession,
    tools: DayTools,
    user: auth.User,
    conversation_id: uuid.UUID,
    now: datetime,
) -> MeetupOffer:
    """The card for a chat. Only the last few messages are read, only now."""
    await chat_app.get_conversation(session, user.id, conversation_id)
    rows = await chat.recent_messages(session, conversation_id, MESSAGES_READ)
    texts = [m.text[:MESSAGE_CHARS] for m in rows]
    result = await assistant.plan_meetup(tools.assistant, texts, deadline_s=LLM_DEADLINE_S)
    if result is not None:
        intent, source = result.value, "llm"
    else:
        intent, source = assistant.MeetupIntent(kind="venue"), "code"
    kinds = list(intent.venue_kinds) or list(DEFAULT_KINDS)

    def offer(**fields: object) -> MeetupOffer:
        base: dict[str, object] = {
            "kind": intent.kind,
            "source": source,
            "starts_at": None,
            "activity": None,
            "venues": [],
            "note": None,
            "attribution": None,
        }
        return MeetupOffer.model_validate(base | fields)

    async def record(out: MeetupOffer) -> MeetupOffer:
        await analytics.record(
            session,
            EventType.MEETUP_SUGGESTED,
            user.id,
            {
                "conversation_id": conversation_id,
                "kind": out.kind,
                "source": out.source,
                "venues": len(out.venues),
                "messages": len(texts),
            },
            occurred_at=now,
        )
        await session.commit()
        return out

    if intent.kind == "unclear":
        return await record(offer(note=NOTE_UNCLEAR))
    starts_at = meetup_time(intent.time, now, user.timezone)
    if starts_at is None:
        return await record(offer(note=NOTE_TOO_LATE))
    if intent.kind == "online":
        return await record(offer(starts_at=starts_at, activity=intent.activity))
    if user.city_id is None:
        return await record(offer(note=NOTE_NO_CITY))
    local_start = starts_at.astimezone(ZoneInfo(user.timezone)).replace(tzinfo=None)
    found = await events.venue_candidates(session, user.city_id, local_start, kinds, VENUES_SHOWN)
    city = await events.get_city(session, user.city_id)
    city_name = city.name if city else ""
    return await record(
        offer(
            starts_at=starts_at,
            venues=[_venue(c, city_name) for c in found],
            note=None if found else NOTE_NO_VENUES,
            attribution=events.ATTRIBUTION if found else None,
        )
    )


async def pick(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    conversation_id: uuid.UUID,
    body: MeetupPick,
    now: datetime,
) -> Coop:
    """Create the co-op for the chosen venue (or online activity) with everyone else in the
    chat invited."""
    await chat_app.get_conversation(session, user.id, conversation_id)
    if (body.venue_id is None) == (body.activity is None):
        raise Problem(422, "validation-failed", detail="Выбери место или онлайн-занятие")
    members = (await chat.member_ids(session, [conversation_id]))[conversation_id]
    friends = [m for m in members if m != user.id]
    if not friends or len(friends) > MAX_FRIENDS:
        raise Problem(422, "validation-failed", detail="В плане может быть до четырёх человек")
    place: Place | None = None
    if body.venue_id is not None:
        found = await events.venue_place(session, body.venue_id)
        if found is None:
            raise Problem(404, "venue-not-found", detail="Такого места нет")
        venue, snapshot = found
        place = Place.model_validate(snapshot)
        title = f"Встреча: {venue.name}"[:120]
    else:
        title = f"Онлайн: {body.activity}"[:120]
    plan = CoopCreateInput(
        title=title,
        category="social",
        duration_min=DEFAULT_DURATION,
        outdoor=False,
        place=place,
        starts_at=body.starts_at,
        friend_ids=friends,
    )
    return await coop_app.create_plan(session, realtime, user, plan, now)
