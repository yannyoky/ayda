import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.realtime import RealtimeDep
from ayda.api.schemas import (
    ChatUploadInput,
    Conversation,
    Coop,
    DirectConversationInput,
    Items,
    MeetupOffer,
    MeetupPick,
    Message,
    MessageEdit,
    MessageInput,
    MessagePage,
    ReadInput,
    UploadSlot,
)
from ayda.app import chat as chat_app
from ayda.app import meetup
from ayda.app.day import DayTools
from ayda.core.problems import Problem
from ayda.core.storage import Storage
from ayda.modules import chat

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


@router.delete("/conversations/{conversation_id}", operation_id="hideConversation", status_code=204)
async def hide_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    await chat_app.hide_conversation(session, user, conversation_id, datetime.now(UTC))
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages", operation_id="listMessages")
async def list_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> MessagePage:
    _, member = await chat_app.get_conversation(session, user.id, conversation_id)
    try:
        messages, next_cursor = await chat.messages_page(
            session, conversation_id, cursor, limit, member.hidden_at
        )
    except chat.CursorError:
        raise Problem(422, "invalid-cursor", detail="Неверный курсор") from None
    items = await chat_app.message_views(session, messages)
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
        session,
        realtime,
        user,
        conversation_id,
        body.text,
        body.client_id,
        datetime.now(UTC),
        body.attachment_id,
    )
    if not created:
        response.status_code = 200
    return message


@router.post(
    "/conversations/{conversation_id}/uploads", operation_id="createChatUpload", status_code=201
)
async def create_chat_upload(
    conversation_id: uuid.UUID,
    body: ChatUploadInput,
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> UploadSlot:
    storage: Storage = request.app.state.storage
    slot = await chat_app.create_upload(
        session,
        storage,
        user,
        conversation_id,
        body.kind,
        body.content_type,
        body.size_bytes,
        _now(),
    )
    return UploadSlot(
        media_id=slot.attachment.id,
        upload_url=slot.upload_url,
        headers=slot.headers,
        expires_at=slot.expires_at,
    )


@router.patch("/conversations/{conversation_id}/messages/{message_id}", operation_id="editMessage")
async def edit_message(
    conversation_id: uuid.UUID,
    message_id: int,
    body: MessageEdit,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Message:
    return await chat_app.edit_message(
        session, realtime, user, conversation_id, message_id, body.text, datetime.now(UTC)
    )


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


def _now() -> datetime:
    return datetime.now(UTC)


def _tools(request: Request) -> DayTools:
    tools: DayTools = request.app.state.day_tools
    return tools


@router.post("/conversations/{conversation_id}/meetup", operation_id="suggestMeetup")
async def suggest_meetup(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    tools: Annotated[DayTools, Depends(_tools)],
) -> MeetupOffer:
    return await meetup.suggest(session, tools, user, conversation_id, _now())


@router.post(
    "/conversations/{conversation_id}/meetup/pick", operation_id="pickMeetup", status_code=201
)
async def pick_meetup(
    conversation_id: uuid.UUID,
    body: MeetupPick,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await meetup.pick(session, realtime, user, conversation_id, body, _now())
