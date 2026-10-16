import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.realtime import RealtimeDep
from ayda.api.schemas import (
    Conversation,
    DirectConversationInput,
    Items,
    Message,
    MessageInput,
    MessagePage,
    ReadInput,
)
from ayda.app import chat as chat_app
from ayda.app.feed import user_summary
from ayda.core.problems import Problem
from ayda.modules import auth, chat

router = APIRouter(tags=["chat"])

Cursor = Annotated[str | None, Query(max_length=200)]
Limit = Annotated[int, Query(ge=1, le=50)]


@router.get("/conversations", operation_id="listConversations")
async def list_conversations(user: CurrentUser, session: DbSession) -> Items[Conversation]:
    rows = await chat.user_conversations(session, user.id)
    return Items(items=await chat_app.build_conversations(session, user.id, rows))


@router.post("/conversations/direct", operation_id="openDirectConversation")
async def open_direct_conversation(
    body: DirectConversationInput, user: CurrentUser, session: DbSession
) -> Conversation:
    return await chat_app.open_direct(session, user, body.user_id, datetime.now(UTC))


@router.get("/conversations/{conversation_id}", operation_id="getConversation")
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Conversation:
    return await chat_app.conversation_view(session, user.id, conversation_id)


@router.get("/conversations/{conversation_id}/messages", operation_id="listMessages")
async def list_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> MessagePage:
    await chat_app.get_conversation(session, user.id, conversation_id)
    try:
        messages, next_cursor = await chat.messages_page(session, conversation_id, cursor, limit)
    except chat.CursorError:
        raise Problem(422, "invalid-cursor", detail="Неверный курсор") from None
    authors = await auth.get_users(session, list({m.author_id for m in messages}))
    items = [
        chat_app.message_schema(m, user_summary(authors.get(m.author_id), m.author_id))
        for m in messages
    ]
    return MessagePage(items=items, next_cursor=next_cursor)


@router.post(
    "/conversations/{conversation_id}/messages", operation_id="sendMessage", status_code=201
)
async def send_message(
    conversation_id: uuid.UUID,
    body: MessageInput,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
    response: Response,
) -> Message:
    message, created = await chat_app.send_message(
        session, realtime, user, conversation_id, body.text, body.client_id, datetime.now(UTC)
    )
    if not created:
        response.status_code = 200
    return message


@router.delete(
    "/conversations/{conversation_id}/messages/{message_id}",
    operation_id="deleteMessage",
    status_code=204,
)
async def delete_message(
    conversation_id: uuid.UUID,
    message_id: int,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Response:
    await chat_app.delete_message(
        session, realtime, user, conversation_id, message_id, datetime.now(UTC)
    )
    return Response(status_code=204)


@router.post(
    "/conversations/{conversation_id}/read", operation_id="markConversationRead", status_code=204
)
async def mark_read(
    conversation_id: uuid.UUID,
    body: ReadInput,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Response:
    await chat_app.mark_read(session, realtime, user, conversation_id, body.last_read_message_id)
    return Response(status_code=204)
