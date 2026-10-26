from datetime import UTC, datetime

from fastapi import APIRouter, Response

from ayda.api.deps import Consented, CurrentUser, DbSession
from ayda.api.schemas import TopEvents
from ayda.app import assistant_chat, top_events
from ayda.core.problems import Problem
from ayda.modules import events

router = APIRouter(tags=["events"], dependencies=[Consented])


@router.get("/events/top", operation_id="listTopEvents")
async def list_top_events(user: CurrentUser, session: DbSession) -> TopEvents:
    items = await top_events.top_nearby(session, user, datetime.now(UTC))
    return TopEvents(items=items, attribution=assistant_chat.EVENTS_ATTRIBUTION)


@router.post("/venues/{venue_id}/closed", operation_id="reportVenueClosed", status_code=204)
async def report_venue_closed(venue_id: int, user: CurrentUser, session: DbSession) -> Response:
    """ "Не работает" on a place card: gone from this user's picks at once, from everyone's
    once a second person says the same, for 30 days."""
    if not await events.report_closed(session, venue_id, user.id, datetime.now(UTC)):
        raise Problem(404, "venue-not-found", detail="Место не найдено")
    await session.commit()
    return Response(status_code=204)
