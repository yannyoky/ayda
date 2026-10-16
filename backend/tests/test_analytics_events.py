import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.db import Database
from ayda.modules import analytics
from ayda.modules.analytics.models import Event


@pytest.fixture
async def session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.sessionmaker() as s:
        yield s


async def test_record_writes_event_with_schema_version(session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    quest_id = uuid.uuid4()

    await analytics.record(
        session,
        analytics.EventType.QUEST_REJECTED,
        user_id,
        {"day_quest_id": quest_id, "reason": "no_time", "replacements_left": 4},
    )
    await session.commit()

    event = (await session.execute(select(Event))).scalar_one()
    assert event.type == "quest_rejected"
    assert event.user_id == user_id
    assert event.schema_version == 1
    assert event.payload == {
        "day_quest_id": str(quest_id),
        "reason": "no_time",
        "replacements_left": 4,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "работаю до 18"},
        {"checkin_text": "x"},
        {"init_data": "query_id=1"},
        {"lat": 54.7, "lon": 20.5},
        {"location": {"x": 1}},
        {"photo_url": "https://s3/x.jpg"},
        {"nested": {"caption": "x"}},
        {"items": [{"first_name": "Саша"}]},
        {"title": "Прогулка"},
        {"note": "free text with spaces"},
        {"note": "https://example.com"},
    ],
)
async def test_payload_with_personal_data_is_rejected(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    with pytest.raises(analytics.PayloadError):
        await analytics.record(session, analytics.EventType.CHECKIN_SUBMITTED, None, payload)


async def test_events_are_append_only(session: AsyncSession) -> None:
    await analytics.record(session, analytics.EventType.POOL_SHOWN, None, {"size": 6})
    await session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("UPDATE analytics.events SET type = 'x'"))
    await session.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("DELETE FROM analytics.events"))
    await session.rollback()


async def test_maintenance_flag_allows_anonymization(session: AsyncSession) -> None:
    await analytics.record(session, analytics.EventType.POOL_SHOWN, uuid.uuid4(), {"size": 6})
    await session.commit()

    await session.execute(text("SET LOCAL ayda.analytics_maintenance = 'on'"))
    await session.execute(text("UPDATE analytics.events SET user_id = gen_random_uuid()"))
    await session.commit()
