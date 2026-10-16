import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.habits.models import UserGoal, UserHabit


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(UserHabit).where(UserHabit.user_id == user_id))
    await session.execute(delete(UserGoal).where(UserGoal.user_id == user_id))
