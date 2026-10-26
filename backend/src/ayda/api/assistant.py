import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from ayda.api.deps import Consented, CurrentUser, DbSession
from ayda.api.schemas import AssistantExchange, AssistantMessageInput, AssistantThread
from ayda.app import assistant_chat
from ayda.app.day import DayTools

router = APIRouter(tags=["assistant"], dependencies=[Consented])


def _now() -> datetime:
    return datetime.now(UTC)


def _tools(request: Request) -> DayTools:
    tools: DayTools = request.app.state.day_tools
    return tools


@router.get("/assistant/messages", operation_id="listAssistantMessages")
async def list_messages(
    user: CurrentUser, session: DbSession, quest_id: Annotated[uuid.UUID | None, Query()] = None
) -> AssistantThread:
    return await assistant_chat.thread(session, user, quest_id, _now())


@router.post("/assistant/messages", operation_id="sendAssistantMessage", status_code=201)
async def send_message(
    body: AssistantMessageInput,
    user: CurrentUser,
    session: DbSession,
    tools: Annotated[DayTools, Depends(_tools)],
) -> AssistantExchange:
    exchange = await assistant_chat.send(session, tools, user, body, _now())
    await session.commit()
    return exchange
