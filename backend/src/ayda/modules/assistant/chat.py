"""Storage of the day chat with the assistant (ADR 0013): one chat per user and local day,
with a topic per quest. Messages go away with the day."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.assistant.models import ChatMessage

Role = str  # "user" | "assistant"

REPLY_CHECKIN = (
    "Записала твой день и собрала квесты под него: выбери, что возьмёшь. "
    "Если хочется что-то обсудить или поменять, пиши сюда."
)
REPLY_EMPTY_CHECKIN = (
    "Собрала квесты по твоему профилю: выбери, что возьмёшь. "
    "Расскажи, какой у тебя день, и я подстрою их."
)


async def topic_messages(
    session: AsyncSession,
    user_id: uuid.UUID,
    day: date,
    quest_id: uuid.UUID | None,
    limit: int | None = None,
) -> list[ChatMessage]:
    """Oldest first; with `limit`, only the last `limit` messages."""
    query = select(ChatMessage).where(
        ChatMessage.user_id == user_id,
        ChatMessage.local_date == day,
        ChatMessage.quest_id.is_(None) if quest_id is None else ChatMessage.quest_id == quest_id,
    )
    if limit is None:
        rows = await session.scalars(query.order_by(ChatMessage.created_at, ChatMessage.id))
        return list(rows)
    rows = await session.scalars(
        query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit)
    )
    return list(reversed(list(rows)))


async def user_messages_today(session: AsyncSession, user_id: uuid.UUID, day: date) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.local_date == day,
            ChatMessage.role == "user",
        )
    )
    return count or 0


async def add_message(
    session: AsyncSession,
    user_id: uuid.UUID,
    day: date,
    quest_id: uuid.UUID | None,
    role: Role,
    text: str,
    now: datetime,
    *,
    source: str | None = None,
    cards: list[dict[str, Any]] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        user_id=user_id,
        local_date=day,
        quest_id=quest_id,
        role=role,
        text=text,
        source=source,
        cards=cards or [],
        created_at=now,
    )
    session.add(message)
    await session.flush()
    return message


async def add_checkin(
    session: AsyncSession, user_id: uuid.UUID, day: date, text: str, now: datetime
) -> None:
    """The check-in is the first message of the day topic; a repeated one adds to it."""
    if text:
        await add_message(session, user_id, day, None, "user", text, now)
    reply = REPLY_CHECKIN if text else REPLY_EMPTY_CHECKIN
    await add_message(session, user_id, day, None, "assistant", reply, now, source="code")


async def purge_before(session: AsyncSession, day: date) -> int:
    """Deletes chats of days before `day` (the caller passes the earliest day still running
    anywhere, so nobody loses today's chat)."""
    result = await session.execute(
        delete(ChatMessage).where(ChatMessage.local_date < day).returning(ChatMessage.id)
    )
    return len(result.all())


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
