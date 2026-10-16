from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import Ladder
from ayda.app.ladder import build_ladder

router = APIRouter(tags=["social"])


@router.get("/ladder", operation_id="getLadder")
async def get_ladder(
    user: CurrentUser, session: DbSession, week: Literal["current", "previous"] = "current"
) -> Ladder:
    return await build_ladder(session, user, datetime.now(UTC), previous=week == "previous")
