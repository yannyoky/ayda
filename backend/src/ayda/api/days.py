import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import CheckinInput, Day, DayQuest, OwnQuestInput, ReplaceInput, Replacement
from ayda.app import day
from ayda.app.day import DayTools

router = APIRouter(tags=["day"])


def get_day_tools(request: Request) -> DayTools:
    tools: DayTools = request.app.state.day_tools
    return tools


Tools = Annotated[DayTools, Depends(get_day_tools)]


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/days/today", operation_id="getToday")
async def get_today(user: CurrentUser, session: DbSession) -> Day:
    return await day.build_day(session, user, _now())


@router.put("/days/today/checkin", operation_id="submitCheckin", status_code=202)
async def submit_checkin(
    body: CheckinInput, user: CurrentUser, session: DbSession, tools: Tools
) -> Day:
    result = await day.submit_checkin(session, user, body, tools, _now())
    await session.commit()
    return result


@router.post("/day-quests", operation_id="addOwnQuest", status_code=201)
async def add_own_quest(body: OwnQuestInput, user: CurrentUser, session: DbSession) -> DayQuest:
    result = await day.add_own_quest(session, user, body, _now())
    await session.commit()
    return result


@router.post("/day-quests/{quest_id}/take", operation_id="takeQuest")
async def take_quest(quest_id: uuid.UUID, user: CurrentUser, session: DbSession) -> DayQuest:
    result = await day.take_quest(session, user, quest_id, _now())
    await session.commit()
    return result


@router.post("/day-quests/{quest_id}/replace", operation_id="replaceQuest")
async def replace_quest(
    quest_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    body: ReplaceInput | None = None,
) -> Replacement:
    reason = body.reason if body else None
    result = await day.replace_quest(session, user, quest_id, reason, _now())
    await session.commit()
    return result
