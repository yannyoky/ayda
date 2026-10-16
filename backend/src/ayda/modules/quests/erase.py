import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.quests.models import Checkin, DayPool, DayQuest, PointsEntry, Streak

CHECKIN_TEXT_TTL = timedelta(days=30)


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    # The ledger is append-only; account erasure is its one maintenance path.
    await session.execute(text("SET LOCAL ayda.points_maintenance = 'on'"))
    await session.execute(delete(PointsEntry).where(PointsEntry.user_id == user_id))
    await session.execute(delete(Streak).where(Streak.user_id == user_id))
    await session.execute(delete(DayQuest).where(DayQuest.user_id == user_id))
    await session.execute(delete(DayPool).where(DayPool.user_id == user_id))
    await session.execute(delete(Checkin).where(Checkin.user_id == user_id))


async def purge_checkin_texts(session: AsyncSession, now: datetime) -> int:
    """Check-in texts are kept 30 days (the parsed tasks stay for the day's history)."""
    result = await session.execute(
        update(Checkin)
        .where(Checkin.text.is_not(None), Checkin.updated_at < now - CHECKIN_TEXT_TTL)
        .values(text=None)
        .returning(Checkin.id)
    )
    return len(result.all())
