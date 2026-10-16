from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ayda.api.deps import AppSettings, CurrentUser
from ayda.api.schemas import RealtimeToken
from ayda.core.problems import Problem
from ayda.core.realtime import Realtime, RealtimeUnavailable, connection_token

router = APIRouter(tags=["chat"])


def get_realtime(request: Request) -> Realtime:
    realtime: Realtime = request.app.state.realtime
    return realtime


RealtimeDep = Annotated[Realtime, Depends(get_realtime)]


@router.post("/realtime/token", operation_id="getRealtimeToken")
async def get_realtime_token(user: CurrentUser, settings: AppSettings) -> RealtimeToken:
    try:
        token = connection_token(settings, user.id, datetime.now(UTC))
    except RealtimeUnavailable:
        raise Problem(503, "realtime-unavailable", detail="Чат временно недоступен") from None
    return RealtimeToken(
        token=token.token, expires_at=token.expires_at, url=token.url, channel=token.channel
    )
