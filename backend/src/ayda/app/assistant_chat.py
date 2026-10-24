"""The day chat with the assistant (M6, ADR 0013).

The check-in opens it; then the user writes in the day topic or in the topic of one of
today's quests. The assistant gets the last messages of the topic and an anonymized context
(mood, interests, weather, the quest), never the name or city. It answers in prose and may ask
code for one action; facts on cards come only from code. Text is never logged, and the chat
is deleted once the day is over.
"""

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import (
    AssistantCard,
    AssistantEvent,
    AssistantExchange,
    AssistantMessage,
    AssistantMessageInput,
    AssistantPlace,
    AssistantThread,
)
from ayda.app import events as events_app
from ayda.app.cooking import recipe_card
from ayda.app.day import DayTools, quest_schema
from ayda.core.problems import Problem
from ayda.modules import analytics, assistant, auth, events, habits, quests
from ayda.modules.analytics import EventType
from ayda.modules.assistant import recipes
from ayda.modules.quests import days as day_clock

DAILY_LIMIT = 40
HISTORY = 10
HISTORY_CHARS = 300
LLM_DEADLINE_S = 12.0

PLACES_SHOWN = 5
EVENTS_SHOWN = 5
EVENT_WEEK = timedelta(days=7)
DISHES_SHOWN = 3
MAX_OFFERED = 5
PLACE_KINDS: dict[str, tuple[str, ...]] = {
    "walk": events.WALK_KINDS,
    "food": ("restaurant", "cafe", "fast_food"),
    "drinks": ("bar", "pub"),
}
MEALS: tuple[tuple[tuple[str, ...], recipes.Meal], ...] = (
    (("завтрак",), "breakfast"),
    (("обед",), "lunch"),
    (("ужин",), "dinner"),
    (("десерт", "сладк"), "dessert"),
    (("перекус",), "snack"),
)

REPLY_UNAVAILABLE = "Сейчас не получается ответить, попробуй чуть позже."
NOTE_NO_CITY = "Укажи город в профиле, и я найду места рядом."
NOTE_NO_PLACES = "Рядом с центром города в карте пока мало таких мест."
NOTE_LOADING = "Загружаю места твоего города из карты. Спроси ещё раз через пару минут."
NOTE_MAP_DOWN = "Карта сейчас не отвечает, попробую загрузить места снова в течение часа."
NOTE_NO_EVENTS = "В афише на эти дни ничего не нашёл."
NOTE_NOT_EXACT = "Точно такого в афише нет, вот что ещё будет."
NOTE_OTHER_REGION = "Афишу я собираю только по твоей области."
NOTE_UNKNOWN_TOWN = "Не знаю такого города, ищу в твоём."
EVENTS_ATTRIBUTION = "Афиша: Timepad и KudaGo"
NOTE_UNKNOWN_FOOD = "Таких продуктов нет в моих рецептах, вот что готовится быстро."
NOTE_ALLERGENS = "Аллергены указаны по рецепту. Состав покупных продуктов проверяй сам."
NOTE_TOO_MANY = "Сегодня уже ждут несколько моих квестов. Возьми или замени один из них."
WHY_QUEST = "Придумали вместе с помощником"

# Obvious requests the code understands without the LLM, checked in this order.
_INTENTS: tuple[tuple[tuple[str, ...], assistant.ChatAction, str], ...] = (
    (
        ("приготов", "рецепт", "меню", "из продукт", "что есть дома", "холодильник"),
        assistant.ChatAction(type="suggest_dishes"),
        "Вот что можно приготовить.",
    ),
    (
        (
            "афиш",
            "событи",
            "мероприят",
            "концерт",
            "выставк",
            "спектакл",
            "театр",
            "стендап",
            "фестивал",
            "лекци",
            "куда сходить",
        ),
        assistant.ChatAction(type="find_events"),
        "Вот что есть в афише.",
    ),
    (
        ("бар", "паб", "выпить"),
        assistant.ChatAction(type="find_places", kind="drinks"),
        "Вот бары и пабы рядом.",
    ),
    (
        ("ресторан", "кафе", "поесть", "поужина", "пообеда", "позавтрака", "кофе"),
        assistant.ChatAction(type="find_places", kind="food"),
        "Вот места, где можно поесть.",
    ),
    (
        ("гуля", "прогул", "парк", "пройтись", "набережн"),
        assistant.ChatAction(type="find_places", kind="walk"),
        "Вот где можно погулять.",
    ),
)


def meal_in(text: str) -> recipes.Meal | None:
    lowered = text.lower()
    return next((meal for words, meal in MEALS if any(w in lowered for w in words)), None)


def code_answer(text: str) -> assistant.ChatAnswer:
    """The answer when no LLM is available: a known request gets its action."""
    lowered = text.lower()
    for words, action, reply in _INTENTS:
        if any(word in lowered for word in words):
            if action.type == "suggest_dishes":
                action = action.model_copy(update={"meal": meal_in(text)})
            return assistant.ChatAnswer(reply=reply, action=action)
    return assistant.ChatAnswer(reply=REPLY_UNAVAILABLE)


# --- actions: code builds every fact on a card ------------------------------------------


async def _places(
    session: AsyncSession, user: auth.User, kind: str, now: datetime
) -> AssistantCard:
    if user.city_id is None:
        return AssistantCard(kind="places", note=NOTE_NO_CITY)
    local = day_clock.local_now(now, user.timezone).replace(tzinfo=None)
    found = await events.venue_candidates(
        session, user.city_id, local, PLACE_KINDS[kind], PLACES_SHOWN
    )
    if not found:
        if not await events.venues_loaded(session, user.city_id):
            state = await events_app.request_venue_load(session, user.city_id, now)
            note = NOTE_LOADING if state == "loading" else NOTE_MAP_DOWN
            return AssistantCard(kind="places", note=note)
        return AssistantCard(kind="places", note=NOTE_NO_PLACES)
    city = await events.get_city(session, user.city_id)
    city_name = city.name if city else ""
    places: list[AssistantPlace] = []
    for c in found:
        links = events.map_links(c.venue.name, city_name)
        places.append(
            AssistantPlace(
                id=c.venue.id,
                name=c.venue.name,
                kind=c.venue.kind,  # pyright: ignore[reportArgumentType]
                address=c.venue.address,
                distance_m=c.distance_m,
                open_now=c.open_now,
                osm_url=events.osm_url(c.venue),
                gis_url=links["2gis"],
                yandex_url=links["yandex"],
            )
        )
    return AssistantCard(kind="places", places=places, attribution=events.ATTRIBUTION)


_TOWN = re.compile(r"\bв(?:о)?\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё]+)?)")
_WHEN: tuple[tuple[tuple[str, ...], assistant.EventWhen], ...] = (
    (("сегодня", "вечером"), "today"),
    (("завтра",), "tomorrow"),
    (("выходн", "суббот", "воскресен"), "weekend"),
)


def when_in(text: str) -> assistant.EventWhen | None:
    lowered = text.lower()
    return next((when for words, when in _WHEN if any(w in lowered for w in words)), None)


def town_in(text: str) -> str | None:
    """A town after "в"/"во" in the user's words, cut to a stem for the city search."""
    match = _TOWN.search(text)
    if match is None:
        return None
    name = match.group(1)
    return name[:-1] if len(name) > 5 and name[-1] in "еиуюоаы" else name


def event_window(
    when: assistant.EventWhen | None, now: datetime, tz: str
) -> tuple[datetime, datetime]:
    """[since, until] in UTC; days end at 04:00 local time like the quest day."""
    today = day_clock.local_day(now, tz)
    if when == "today":
        return now, day_clock.day_expires_at(today, tz)
    if when == "tomorrow":
        return day_clock.day_expires_at(today, tz), day_clock.day_expires_at(
            today + timedelta(days=1), tz
        )
    if when == "weekend":
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:
            saturday = today - timedelta(days=1)
        since = max(now, day_clock.day_expires_at(saturday - timedelta(days=1), tz))
        return since, day_clock.day_expires_at(saturday + timedelta(days=1), tz)
    return now, now + EVENT_WEEK


def _event_rank(
    hit: events.RegionEvent, interest: events_app.Interest, home: int, now: datetime
) -> tuple[float, datetime, int]:
    """Interest first; a far town and a far date each cost up to about one point."""
    hours = max((hit.listing.starts_at - now).total_seconds() / 3600, 0)
    score = events_app.interest_score(hit.listing, interest)
    score += 0.5 if hit.listing.city_id == home else -min(hit.distance_m / 100_000, 1.5)
    score -= min(hours / 72, 1)
    return (-score, hit.listing.starts_at, hit.listing.id)


def event_card(hit: events.RegionEvent) -> AssistantEvent:
    x = hit.listing
    return AssistantEvent(
        id=x.id,
        title=x.title,
        starts_at=x.starts_at,
        ends_at=x.ends_at,
        venue=x.venue,
        address=x.address,
        city=hit.city_name,
        distance_km=round(hit.distance_m / 1000, 1),
        category=x.category,  # pyright: ignore[reportArgumentType]
        is_free=x.is_free,
        price_min=x.price_min,
        url=x.url,
        source=x.source,
    )


async def _events(
    session: AsyncSession,
    user: auth.User,
    action: assistant.ChatAction,
    text: str,
    now: datetime,
) -> AssistantCard:
    """Listings of the user's region (or of the town they named in it), ranked by interest
    (ADR 0015)."""
    if user.city_id is None:
        return AssistantCard(kind="events", note=NOTE_NO_CITY)
    home = await events.get_city(session, user.city_id)
    if home is None:
        return AssistantCard(kind="events", note=NOTE_NO_CITY)
    target, note = home, None
    named = action.place or town_in(text)
    if named:
        found = await events.search_cities(session, named, 1)
        if not found:
            note = NOTE_UNKNOWN_TOWN if action.place else None
        elif found[0].region_code != home.region_code:
            return AssistantCard(kind="events", note=NOTE_OTHER_REGION)
        else:
            target = found[0]
    since, until = event_window(action.when or when_in(text), now, user.timezone)
    hits = await events.region_events(session, target.id, since, until)
    # Without a query from the LLM, words of the message itself; the town is not a topic.
    words = events_app.stems(action.query or text)
    if named:
        words = tuple(w for w in words if not named.lower().replace("ё", "е").startswith(w[:4]))
    declared = await events_app.declared_interests(session, user.id)
    interest = events_app.Interest(
        asked=words,
        category=action.category,
        interests=declared[0],
        tags=declared[1],
        taste=await events_app.load_taste(
            session, user.id, day_clock.local_day(now, user.timezone)
        ),
    )
    hits.sort(key=lambda h: _event_rank(h, interest, target.id, now))
    if action.query and hits and events_app.interest_score(hits[0].listing, interest) < 3:
        note = note or NOTE_NOT_EXACT
    seen: set[str] = set()
    shown: list[AssistantEvent] = []
    for hit in hits:
        key = hit.listing.title.casefold()
        if key in seen:
            continue
        seen.add(key)
        shown.append(event_card(hit))
        if len(shown) == EVENTS_SHOWN:
            break
    if not shown:
        return AssistantCard(kind="events", note=note or NOTE_NO_EVENTS)
    return AssistantCard(kind="events", events=shown, note=note, attribution=EVENTS_ATTRIBUTION)


def dishes_card(named: list[str], meal: recipes.Meal | None, listed: bool) -> AssistantCard:
    """Recipes from the catalog for what the user has at home (ADR 0012 + 0013). `listed`:
    `named` are products the LLM picked out, not the whole message."""
    rb = recipes.book()
    have = recipes.match_ingredients(rb, named)
    found = (
        recipes.dishes_from(rb, have, meal, DISHES_SHOWN)
        or recipes.dishes_from(rb, have, None, DISHES_SHOWN)
        if have
        else []
    )
    note = NOTE_ALLERGENS
    if not found:
        found = recipes.dishes_from(rb, (), meal, DISHES_SHOWN)
        note = NOTE_UNKNOWN_FOOD if listed else NOTE_ALLERGENS
    cards = [
        recipe_card(d.recipe, rb, f"Есть дома: {d.have} из {d.need}" if d.have else None)
        for d in found
    ]
    return AssistantCard(kind="dishes", recipes=cards, note=note)


async def _quest(
    session: AsyncSession, user: auth.User, day: date, action: assistant.ChatAction, now: datetime
) -> AssistantCard:
    assert action.title and action.category and action.duration_min
    new = quests.NewQuest(
        source="custom",
        title=action.title,
        category=action.category,
        duration_min=action.duration_min,
        why=WHY_QUEST,
    )
    row = await quests.offer_quest(
        session,
        user.id,
        day,
        new,
        day_clock.day_expires_at(day, user.timezone),
        now,
        MAX_OFFERED,
    )
    if row is None:
        return AssistantCard(kind="quest", note=NOTE_TOO_MANY)
    return AssistantCard(kind="quest", quest=quest_schema(row))


async def run_action(
    session: AsyncSession,
    user: auth.User,
    day: date,
    action: assistant.ChatAction | None,
    text: str,
    now: datetime,
) -> list[AssistantCard]:
    if action is None:
        return []
    if action.type == "find_places" and action.kind is not None:
        return [await _places(session, user, action.kind, now)]
    if action.type == "find_events":
        return [await _events(session, user, action, text, now)]
    if action.type == "suggest_dishes":
        meal = action.meal or meal_in(text)
        if action.ingredients:
            return [dishes_card(action.ingredients, meal, listed=True)]
        return [dishes_card([text], meal, listed=False)]
    if action.type == "suggest_quest":
        return [await _quest(session, user, day, action, now)]
    return []


def _items(card: AssistantCard) -> int:
    return len(card.places) + len(card.events) + len(card.recipes) + (1 if card.quest else 0)


def message_schema(message: assistant.chat.ChatMessage) -> AssistantMessage:
    return AssistantMessage(
        id=message.id,
        role=message.role,  # pyright: ignore[reportArgumentType]
        text=message.text,
        quest_id=message.quest_id,
        source=message.source,  # pyright: ignore[reportArgumentType]
        cards=[AssistantCard.model_validate(card) for card in message.cards],
        created_at=message.created_at,
    )


async def _topic_quest(
    session: AsyncSession, user_id: uuid.UUID, day: date, quest_id: uuid.UUID | None
) -> quests.DayQuest | None:
    if quest_id is None:
        return None
    pool = await quests.get_pool(session, user_id, day)
    found = (
        next((q for q in await quests.day_quests(session, pool.id) if q.id == quest_id), None)
        if pool
        else None
    )
    if found is None or found.state == "replaced":
        raise Problem(404, "quest-not-found", detail="Такого квеста сегодня нет")
    return found


async def _left(session: AsyncSession, user_id: uuid.UUID, day: date) -> int:
    used = await assistant.chat.user_messages_today(session, user_id, day)
    return max(DAILY_LIMIT - used, 0)


async def thread(
    session: AsyncSession, user: auth.User, quest_id: uuid.UUID | None, now: datetime
) -> AssistantThread:
    day = day_clock.local_day(now, user.timezone)
    await _topic_quest(session, user.id, day, quest_id)
    rows = await assistant.chat.topic_messages(session, user.id, day, quest_id)
    return AssistantThread(
        items=[message_schema(m) for m in rows], messages_left=await _left(session, user.id, day)
    )


async def _context(
    session: AsyncSession, user: auth.User, day: date, quest: quests.DayQuest | None
) -> assistant.ChatContext:
    checkin = await quests.get_checkin(session, user.id, day)
    pool = await quests.get_pool(session, user.id, day)
    today = (
        [q.title for q in await quests.day_quests(session, pool.id) if q.state != "replaced"]
        if pool
        else []
    )
    return assistant.ChatContext(
        mood=checkin.mood if checkin else None,
        interests=await habits.list_interests(session, user.id),
        weather=pool.weather if pool else None,
        quest=assistant.ChatQuest(quest.title, quest.category, quest.duration_min, quest.state)
        if quest
        else None,
        today=today,
    )


async def send(
    session: AsyncSession,
    tools: DayTools,
    user: auth.User,
    body: AssistantMessageInput,
    now: datetime,
) -> AssistantExchange:
    day = day_clock.local_day(now, user.timezone)
    quest = await _topic_quest(session, user.id, day, body.quest_id)
    left = await _left(session, user.id, day)
    if left == 0:
        raise Problem(429, "assistant-limit", detail="На сегодня сообщения помощнику закончились")
    text = body.text.strip()
    if not text:
        raise Problem(422, "validation-failed", detail="Напиши сообщение")

    earlier = await assistant.chat.topic_messages(
        session, user.id, day, body.quest_id, limit=HISTORY - 1
    )
    sent = await assistant.chat.add_message(session, user.id, day, body.quest_id, "user", text, now)
    history = [(m.role, m.text[:HISTORY_CHARS]) for m in earlier] + [("user", text[:HISTORY_CHARS])]
    context = await _context(session, user, day, quest)
    result = await assistant.chat_reply(tools.assistant, context, history, LLM_DEADLINE_S)
    answer, source = (result.value, "llm") if result else (code_answer(text), "code")
    cards = await run_action(session, user, day, answer.action, text, now)
    stored: list[dict[str, Any]] = [c.model_dump(mode="json") for c in cards]

    reply = await assistant.chat.add_message(
        session,
        user.id,
        day,
        body.quest_id,
        "assistant",
        answer.reply,
        now,
        source=source,
        cards=stored,
    )
    # Counts and codes only: neither the user's text nor the answer leaves the chat table.
    await analytics.record(
        session,
        EventType.ASSISTANT_MESSAGE,
        user.id,
        {
            "topic": "quest" if quest else "day",
            "day_quest_id": quest.id if quest else None,
            "action": answer.action.type if answer.action else None,
            "cards": len(cards),
            "items": sum(_items(c) for c in cards),
            "source": source,
            "provider": result.provider if result else "code",
            "history": len(earlier),
        },
        occurred_at=now,
    )
    return AssistantExchange(
        sent=message_schema(sent), reply=message_schema(reply), messages_left=left - 1
    )
