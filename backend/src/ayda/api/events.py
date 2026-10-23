from datetime import UTC, datetime

from fastapi import APIRouter

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import TopEvents
from ayda.app import assistant_chat, top_events

router = APIRouter(tags=["events"])


@router.get("/events/top", operation_id="listTopEvents")
async def list_top_events(user: CurrentUser, session: DbSession) -> TopEvents:
    items = await top_events.top_nearby(session, user, datetime.now(UTC))
    return TopEvents(items=items, attribution=assistant_chat.EVENTS_ATTRIBUTION)
