import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.habits.models import UserHabit, UserInterest, UserInterestTag


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(UserHabit).where(UserHabit.user_id == user_id))
    await session.execute(delete(UserInterest).where(UserInterest.user_id == user_id))
    await session.execute(delete(UserInterestTag).where(UserInterestTag.user_id == user_id))
