"""Conversations, members and messages. Who may write where (friendship, co-op membership)
is decided by the application layer; this module only stores and reads."""

import base64
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.chat.models import Conversation, Member, Message

MAX_MESSAGES_PER_MINUTE = 30


class CursorError(ValueError):
    pass


class MessageLimitError(Exception):
    pass


def dm_key(a: uuid.UUID, b: uuid.UUID) -> str:
    low, high = sorted((a, b))
    return f"{low}:{high}"


def _encode_cursor(message_id: int) -> str:
    return base64.urlsafe_b64encode(str(message_id).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
    except ValueError as exc:
        raise CursorError(str(exc)) from None


async def open_dm(session: AsyncSession, a: uuid.UUID, b: uuid.UUID, now: datetime) -> Conversation:
    """The direct chat of two users, created on first use (safe under concurrency)."""
    key = dm_key(a, b)
    existing = await session.scalar(select(Conversation).where(Conversation.dm_key == key))
    if existing is not None:
        return existing
    conversation_id = (
        await session.execute(
            insert(Conversation)
            .values(id=uuid7(), kind="dm", dm_key=key, created_at=now)
            .on_conflict_do_nothing(index_elements=[Conversation.dm_key])
            .returning(Conversation.id)
        )
    ).scalar_one_or_none()
    if conversation_id is not None:
        await session.execute(
            insert(Member).values(
                [
                    {"conversation_id": conversation_id, "user_id": u, "joined_at": now}
                    for u in (a, b)
                ]
            )
        )
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.dm_key == key)
        .execution_options(populate_existing=True)
    )
    assert conversation is not None
    return conversation


async def create_group(
    session: AsyncSession, coop_id: uuid.UUID, user_ids: Sequence[uuid.UUID], now: datetime
) -> Conversation:
    """The chat of a co-op quest."""
    conversation = Conversation(kind="coop", coop_id=coop_id, created_at=now)
    session.add(conversation)
    await session.flush()
    for user_id in dict.fromkeys(user_ids):
        await add_member(session, conversation.id, user_id, now)
    return conversation


async def add_member(
    session: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> None:
    await session.execute(
        insert(Member)
        .values(conversation_id=conversation_id, user_id=user_id, joined_at=now)
        .on_conflict_do_nothing()
    )


async def conversation_for_coop(session: AsyncSession, coop_id: uuid.UUID) -> Conversation | None:
    return await session.scalar(select(Conversation).where(Conversation.coop_id == coop_id))


async def conversations_for_coops(
    session: AsyncSession, coop_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """coop id -> its chat id."""
    if not coop_ids:
        return {}
    rows = await session.execute(
        select(Conversation.coop_id, Conversation.id).where(Conversation.coop_id.in_(coop_ids))
    )
    return {c: i for c, i in rows if c is not None}


async def membership(
    session: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Conversation, Member] | None:
    row = (
        await session.execute(
            select(Conversation, Member)
            .join(Member, Member.conversation_id == Conversation.id)
            .where(Conversation.id == conversation_id, Member.user_id == user_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def user_conversations(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Conversation, Member]]:
    """Latest activity first."""
    rows = await session.execute(
        select(Conversation, Member)
        .join(Member, Member.conversation_id == Conversation.id)
        .where(Member.user_id == user_id)
        .order_by(
            func.coalesce(Conversation.last_message_at, Conversation.created_at).desc(),
            Conversation.id.desc(),
        )
    )
    return [(c, m) for c, m in rows]


async def member_ids(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    rows = await session.execute(
        select(Member.conversation_id, Member.user_id)
        .where(Member.conversation_id.in_(conversation_ids))
        .order_by(Member.joined_at, Member.user_id)
    )
    out: dict[uuid.UUID, list[uuid.UUID]] = {c: [] for c in conversation_ids}
    for conversation_id, user_id in rows:
        out[conversation_id].append(user_id)
    return out


async def find_by_client_id(
    session: AsyncSession, author_id: uuid.UUID, client_id: uuid.UUID
) -> Message | None:
    return await session.scalar(
        select(Message).where(Message.author_id == author_id, Message.client_id == client_id)
    )


async def add_message(
    session: AsyncSession,
    conversation: Conversation,
    author_id: uuid.UUID,
    text: str,
    client_id: uuid.UUID,
    now: datetime,
) -> tuple[Message, bool]:
    """Returns (message, created). A repeated `client_id` returns the first message."""
    existing = await find_by_client_id(session, author_id, client_id)
    if existing is not None:
        return existing, False
    recent = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.author_id == author_id, Message.created_at > now - timedelta(minutes=1))
    )
    if (recent or 0) >= MAX_MESSAGES_PER_MINUTE:
        raise MessageLimitError
    message_id = (
        await session.execute(
            insert(Message)
            .values(
                conversation_id=conversation.id,
                author_id=author_id,
                client_id=client_id,
                text=text,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=[Message.author_id, Message.client_id])
            .returning(Message.id)
        )
    ).scalar_one_or_none()
    if message_id is None:  # a concurrent retry won the race
        existing = await find_by_client_id(session, author_id, client_id)
        assert existing is not None
        return existing, False
    conversation.last_message_at = now
    # The author has read everything up to their own message.
    await session.execute(
        update(Member)
        .where(Member.conversation_id == conversation.id, Member.user_id == author_id)
        .values(last_read_message_id=message_id)
    )
    message = await session.get(Message, message_id)
    assert message is not None
    return message, True


async def get_message(
    session: AsyncSession, conversation_id: uuid.UUID, message_id: int
) -> Message | None:
    message = await session.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id or message.deleted_at:
        return None
    return message


async def delete_message(session: AsyncSession, message: Message, now: datetime) -> None:
    """The text is removed right away; the row stays so ids and read marks keep working."""
    message.deleted_at = now
    message.text = "-"


async def messages_page(
    session: AsyncSession, conversation_id: uuid.UUID, cursor: str | None, limit: int
) -> tuple[list[Message], str | None]:
    """Newest first."""
    query = select(Message).where(
        Message.conversation_id == conversation_id, Message.deleted_at.is_(None)
    )
    if cursor:
        query = query.where(Message.id < _decode_cursor(cursor))
    rows = list(await session.scalars(query.order_by(Message.id.desc()).limit(limit + 1)))
    next_cursor = _encode_cursor(rows[limit - 1].id) if len(rows) > limit else None
    return rows[:limit], next_cursor


async def last_messages(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Message]:
    if not conversation_ids:
        return {}
    latest = (
        select(Message.conversation_id, func.max(Message.id).label("id"))
        .where(Message.conversation_id.in_(conversation_ids), Message.deleted_at.is_(None))
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = await session.scalars(select(Message).join(latest, Message.id == latest.c.id))
    return {m.conversation_id: m for m in rows}


async def recent_messages(
    session: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[Message]:
    """The last `limit` messages that are not deleted, oldest first."""
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


async def unread_counts(
    session: AsyncSession, user_id: uuid.UUID, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not conversation_ids:
        return {}
    rows = await session.execute(
        select(Message.conversation_id, func.count())
        .join(
            Member,
            and_(Member.conversation_id == Message.conversation_id, Member.user_id == user_id),
        )
        .where(
            Message.conversation_id.in_(conversation_ids),
            Message.author_id != user_id,
            Message.deleted_at.is_(None),
            Message.id > func.coalesce(Member.last_read_message_id, 0),
        )
        .group_by(Message.conversation_id)
    )
    counts = dict.fromkeys(conversation_ids, 0)
    counts.update({c: n for c, n in rows})
    return counts


async def mark_read(session: AsyncSession, member: Member, message_id: int) -> int | None:
    """Move the read mark forward (never back, never past the last message).
    Returns the new mark, or None when nothing changed."""
    newest = await session.scalar(
        select(func.max(Message.id)).where(Message.conversation_id == member.conversation_id)
    )
    target = min(message_id, newest or 0)
    if target <= (member.last_read_message_id or 0):
        return None
    member.last_read_message_id = target
    return target


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete the user's messages and memberships, then chats nobody is left in."""
    await session.execute(delete(Message).where(Message.author_id == user_id))
    await session.execute(delete(Member).where(Member.user_id == user_id))
    await session.execute(
        delete(Conversation).where(
            ~select(Member.user_id).where(Member.conversation_id == Conversation.id).exists()
        )
    )
