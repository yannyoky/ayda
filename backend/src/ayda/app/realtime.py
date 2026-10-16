"""Publishing realtime events after a write is committed (ADR 0007).

Callers commit their change first, then call `publish` with an event kind and ids. The event
is built from current data by the kind's builder, so a retry job carries ids only, never
message text. If Centrifugo is down, the `realtime.publish` job retries the broadcast.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core import jobs
from ayda.core.realtime import Realtime, RealtimeUnavailable

log = logging.getLogger(__name__)

PUBLISH_JOB = "realtime.publish"


@dataclass(frozen=True)
class Delivery:
    user_ids: Sequence[uuid.UUID]
    event: Mapping[str, Any]


# kind -> builder; None from a builder means there is nothing to deliver anymore.
Builder = Callable[[AsyncSession, Mapping[str, Any]], Awaitable[Delivery | None]]
BUILDERS: dict[str, Builder] = {}


async def deliver(
    session: AsyncSession, realtime: Realtime, kind: str, params: Mapping[str, Any]
) -> None:
    """Build and broadcast now; raises RealtimeUnavailable (used by the retry job)."""
    delivery = await BUILDERS[kind](session, params)
    if delivery is not None:
        await realtime.broadcast(delivery.user_ids, delivery.event)


async def publish(
    session: AsyncSession, realtime: Realtime, kind: str, params: Mapping[str, Any]
) -> None:
    """Broadcast after the caller's commit; on failure queue a retry and commit it."""
    if not realtime.enabled:
        return
    try:
        await deliver(session, realtime, kind, params)
    except RealtimeUnavailable as exc:
        log.warning("realtime publish of %s failed (%s), queued a retry", kind, exc)
        await jobs.enqueue(session, PUBLISH_JOB, {"kind": kind, "params": dict(params)})
        await session.commit()
