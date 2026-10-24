"""Direct messages across modules (US-17): chats (chat), names (auth), friendships (social),
realtime delivery (ADR 0007) and bot notifications without the message text."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import Conversation, Message, UserSummary
from ayda.app.feed import DELETED_NAME, user_summary
from ayda.app.notifications import RENDERERS, Renderer, app_button, notify
from ayda.app.notifications import Message as BotMessage
from ayda.app.realtime import BUILDERS, Delivery, publish
from ayda.core.config import Settings
from ayda.core.problems import Problem
from ayda.core.realtime import Realtime
from ayda.modules import analytics, auth, chat, quests, social
from ayda.modules.analytics import EventType

MESSAGE_CREATED = "chat.message_created"
MESSAGE_DELETED = "chat.message_deleted"
CONVERSATION_READ = "chat.conversation_read"
NOTIFY_KIND = "chat.message"
# The bot waits a minute (the message may be read in the app by then) and sends at most
# one notice per chat and person every 10 minutes.
NOTIFY_DELAY = timedelta(minutes=1)
NOTIFY_BUCKET_S = 600
COOP_TITLE = "Совместный квест"
# A co-op chat is deleted for everyone this long after its quest is over.
COOP_CHAT_TTL = timedelta(days=30)


def not_found() -> Problem:
    return Problem(404, "conversation-not-found", detail="Чат не найден")


def message_schema(message: chat.Message, author: UserSummary) -> Message:
    return Message(
        id=message.id,
        conversation_id=message.conversation_id,
        author=author,
        text=message.text,
        created_at=message.created_at,
        client_id=message.client_id,
    )


async def _can_send(
    session: AsyncSession,
    conversation: chat.Conversation,
    user_id: uuid.UUID,
    others: Sequence[uuid.UUID],
    alive: Mapping[uuid.UUID, bool],
) -> bool:
    if conversation.kind != "dm":
        return True
    return (
        len(others) == 1
        and alive.get(others[0], False)
        and await social.are_friends(session, user_id, others[0])
    )


def _deletes_at(
    conversation: chat.Conversation, ends: Mapping[uuid.UUID, datetime]
) -> datetime | None:
    end = ends.get(conversation.coop_id) if conversation.coop_id else None
    return end + COOP_CHAT_TTL if end else None


async def build_conversations(
    session: AsyncSession, user_id: uuid.UUID, rows: Sequence[tuple[chat.Conversation, chat.Member]]
) -> list[Conversation]:
    ids = [c.id for c, _ in rows]
    members = await chat.member_ids(session, ids)
    last = await chat.last_messages(session, ids)
    unread = await chat.unread_counts(session, user_id, ids)
    people = {u for us in members.values() for u in us} | {m.author_id for m in last.values()}
    users = await auth.get_users(session, list(people))
    coop_ids = [c.coop_id for c, _ in rows if c.coop_id is not None]
    titles = await quests.coop.coop_titles(session, coop_ids)
    ends = await quests.coop.coop_ends(session, coop_ids)
    alive = {u: users[u].deletion_requested_at is None for u in users}
    out: list[Conversation] = []
    for conversation, member in rows:
        others = [u for u in members[conversation.id] if u != user_id]
        summaries = [user_summary(users.get(u), u) for u in others]
        dm = conversation.kind == "dm"
        peer = summaries[0] if dm and summaries else None
        message = last.get(conversation.id)
        out.append(
            Conversation(
                id=conversation.id,
                kind="dm" if dm else "coop",
                title=peer.first_name
                if peer
                else DELETED_NAME
                if dm
                else titles.get(conversation.coop_id or conversation.id, COOP_TITLE),
                peer=peer,
                coop_id=conversation.coop_id,
                members=summaries,
                can_send=await _can_send(session, conversation, user_id, others, alive),
                last_message=message_schema(
                    message, user_summary(users.get(message.author_id), message.author_id)
                )
                if message
                else None,
                unread_count=unread[conversation.id],
                last_read_message_id=member.last_read_message_id,
                updated_at=conversation.last_message_at or conversation.created_at,
                deletes_at=_deletes_at(conversation, ends),
            )
        )
    return out


async def get_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> tuple[chat.Conversation, chat.Member]:
    found = await chat.membership(session, conversation_id, user_id)
    if found is None:
        raise not_found()
    return found


async def conversation_view(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    [view] = await build_conversations(
        session, user_id, [await get_conversation(session, user_id, conversation_id)]
    )
    return view


async def open_direct(
    session: AsyncSession, user: auth.User, friend_id: uuid.UUID, now: datetime
) -> Conversation:
    friend = await auth.get_user(session, friend_id)
    if (
        friend is None
        or friend.deletion_requested_at is not None
        or not await social.are_friends(session, user.id, friend_id)
    ):
        raise Problem(403, "not-friends", detail="Писать можно только друзьям")
    conversation = await chat.open_dm(session, user.id, friend_id, now)
    await session.commit()
    return await conversation_view(session, user.id, conversation.id)


async def send_message(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    conversation_id: uuid.UUID,
    text: str,
    client_id: uuid.UUID,
    now: datetime,
) -> tuple[Message, bool]:
    """Save, commit, then publish; returns (message, created)."""
    conversation, _ = await get_conversation(session, user.id, conversation_id)
    members = (await chat.member_ids(session, [conversation.id]))[conversation.id]
    others = [u for u in members if u != user.id]
    users = await auth.get_users(session, others)
    alive = {u: users[u].deletion_requested_at is None for u in users}
    repeated = await chat.find_by_client_id(session, user.id, client_id)
    if repeated is None and not await _can_send(session, conversation, user.id, others, alive):
        raise Problem(403, "chat-closed", detail="Этот чат закрыт для новых сообщений")
    try:
        message, created = await chat.add_message(
            session, conversation, user.id, text, client_id, now
        )
    except chat.MessageLimitError:
        raise Problem(429, "too-many-messages", detail="Слишком много сообщений") from None
    if message.conversation_id != conversation.id:  # client_id reused in another chat
        raise Problem(422, "client-id-reused", detail="Этот client_id уже использован")
    if created:
        await analytics.record(
            session,
            EventType.MESSAGE_SENT,
            user.id,
            {"conversation_id": conversation.id, "kind": conversation.kind},
            occurred_at=now,
        )
        bucket = int(now.timestamp()) // NOTIFY_BUCKET_S
        for other in others:
            await notify(
                session,
                other,
                NOTIFY_KIND,
                {"conversation_id": str(conversation.id), "message_id": message.id},
                dedupe_key=f"{NOTIFY_KIND}:{other}:{conversation.id}:{bucket}",
                run_at=now + NOTIFY_DELAY,
            )
    await session.commit()
    if created:
        await publish(session, realtime, MESSAGE_CREATED, {"message_id": message.id})
    return message_schema(message, user_summary(user, user.id)), created


async def delete_message(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    conversation_id: uuid.UUID,
    message_id: int,
    now: datetime,
) -> None:
    await get_conversation(session, user.id, conversation_id)
    message = await chat.get_message(session, conversation_id, message_id)
    if message is None:
        raise Problem(404, "message-not-found", detail="Сообщение не найдено")
    if message.author_id != user.id:
        raise Problem(403, "not-your-message", detail="Удалить можно только своё сообщение")
    await chat.delete_message(session, message, now)
    await session.commit()
    await publish(
        session,
        realtime,
        MESSAGE_DELETED,
        {"conversation_id": str(conversation_id), "message_id": message_id},
    )


async def hide_conversation(
    session: AsyncSession, user: auth.User, conversation_id: uuid.UUID, now: datetime
) -> None:
    """ "Удалить у себя": the chat leaves this user's list with its messages so far; the
    others keep it. A new message brings it back with only what came after."""
    _, member = await get_conversation(session, user.id, conversation_id)
    await chat.hide(session, member, now)
    await session.commit()


async def purge_ended_coop_chats(session: AsyncSession, now: datetime) -> int:
    """Delete co-op chats 30 days after their quest is over, for everyone."""
    coops = await quests.coop.ended_before(session, now - COOP_CHAT_TTL)
    chats = await chat.conversations_for_coops(session, coops)
    return await chat.delete_conversations(session, list(chats.values()))


async def mark_read(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    conversation_id: uuid.UUID,
    message_id: int,
) -> None:
    _, member = await get_conversation(session, user.id, conversation_id)
    mark = await chat.mark_read(session, member, message_id)
    await session.commit()
    if mark is not None:
        await publish(
            session,
            realtime,
            CONVERSATION_READ,
            {"conversation_id": str(conversation_id), "user_id": str(user.id), "message_id": mark},
        )


# --- realtime events --------------------------------------------------------------------


async def _members(session: AsyncSession, conversation_id: uuid.UUID) -> list[uuid.UUID]:
    return (await chat.member_ids(session, [conversation_id]))[conversation_id]


async def _message_created(session: AsyncSession, params: Mapping[str, Any]) -> Delivery | None:
    message = await session.get(chat.Message, int(params["message_id"]))
    if message is None or message.deleted_at is not None:
        return None
    author = await auth.get_user(session, message.author_id)
    data = message_schema(message, user_summary(author, message.author_id))
    return Delivery(
        await _members(session, message.conversation_id),
        {
            "type": "message.created",
            "conversation_id": str(message.conversation_id),
            "message": data.model_dump(mode="json"),
        },
    )


async def _message_deleted(session: AsyncSession, params: Mapping[str, Any]) -> Delivery | None:
    conversation_id = uuid.UUID(str(params["conversation_id"]))
    return Delivery(
        await _members(session, conversation_id),
        {
            "type": "message.deleted",
            "conversation_id": str(conversation_id),
            "message_id": int(params["message_id"]),
        },
    )


async def _conversation_read(session: AsyncSession, params: Mapping[str, Any]) -> Delivery | None:
    conversation_id = uuid.UUID(str(params["conversation_id"]))
    return Delivery(
        await _members(session, conversation_id),
        {
            "type": "conversation.read",
            "conversation_id": str(conversation_id),
            "user_id": str(params["user_id"]),
            "last_read_message_id": int(params["message_id"]),
        },
    )


BUILDERS[MESSAGE_CREATED] = _message_created
BUILDERS[MESSAGE_DELETED] = _message_deleted
BUILDERS[CONVERSATION_READ] = _conversation_read


# --- bot notice -------------------------------------------------------------------------


def message_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> BotMessage | None:
        conversation_id = uuid.UUID(str(params["conversation_id"]))
        found = await chat.membership(session, conversation_id, user.id)
        if found is None:
            return None
        conversation, member = found
        if (member.last_read_message_id or 0) >= int(params["message_id"]):
            return None  # already read in the app
        if not (await chat.unread_counts(session, user.id, [conversation_id]))[conversation_id]:
            return None
        button = app_button(settings, "Открыть чат", start_param=f"c{conversation_id.hex}")
        if conversation.kind == "dm":
            message = await session.get(chat.Message, int(params["message_id"]))
            author = await auth.get_user(session, message.author_id) if message else None
            if author is None or author.deletion_requested_at is not None:
                return None
            return BotMessage(f"Тебе пишет {author.first_name} 💬", button)
        titles = await quests.coop.coop_titles(
            session, [conversation.coop_id] if conversation.coop_id else []
        )
        title = titles.get(conversation.coop_id) if conversation.coop_id else None
        where = f"«{title}»" if title else "совместного квеста"
        return BotMessage(f"Новое сообщение в чате {where} 💬", button)

    return render


def register(settings: Settings) -> None:
    RENDERERS[NOTIFY_KIND] = message_renderer(settings)
