"""The day chat with the assistant (M6, ADR 0013).

The check-in opens it; then the user writes in the day topic or in the topic of one of
today's quests. The assistant gets the last messages of the topic and an anonymized context
(mood, goals, weather, the quest), never the name or city. It answers in prose and may ask
code for one action; facts on cards come only from code. Text is never logged, and the chat
is deleted once the day is over.
"""

import uuid
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import (
    AssistantCard,
    AssistantExchange,
    AssistantMessage,
    AssistantMessageInput,
    AssistantThread,
)
from ayda.app.day import DayTools
from ayda.core.problems import Problem
from ayda.modules import analytics, assistant, auth, habits, quests
from ayda.modules.analytics import EventType
from ayda.modules.quests import days as day_clock

DAILY_LIMIT = 40
HISTORY = 10
HISTORY_CHARS = 300
LLM_DEADLINE_S = 12.0

REPLY_UNAVAILABLE = "Сейчас не получается ответить, попробуй чуть позже."

# Obvious requests the code understands without the LLM, checked in this order.
_INTENTS: tuple[tuple[tuple[str, ...], assistant.ChatAction, str], ...] = (
    (
        ("приготов", "рецепт", "меню", "из продукт", "что есть дома", "холодильник"),
        assistant.ChatAction(type="suggest_dishes"),
        "Вот что можно приготовить.",
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


def code_answer(text: str) -> assistant.ChatAnswer:
    """The answer when no LLM is available: a known request gets its action."""
    lowered = text.lower()
    for words, action, reply in _INTENTS:
        if any(word in lowered for word in words):
            return assistant.ChatAnswer(reply=reply, action=action)
    return assistant.ChatAnswer(reply=REPLY_UNAVAILABLE)


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
        goals=await habits.list_goals(session, user.id),
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

    reply = await assistant.chat.add_message(
        session,
        user.id,
        day,
        body.quest_id,
        "assistant",
        answer.reply,
        now,
        source=source,
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
            "cards": len(reply.cards),
            "source": source,
            "provider": result.provider if result else "code",
            "history": len(earlier),
        },
        occurred_at=now,
    )
    return AssistantExchange(
        sent=message_schema(sent), reply=message_schema(reply), messages_left=left - 1
    )
