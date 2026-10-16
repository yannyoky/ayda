import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.habits.goals import GOAL_CODES, MAX_GOALS
from ayda.modules.habits.models import UserGoal, UserHabit

Direction = Literal["more", "less"]
MAX_HABITS = 20


class GoalsError(ValueError):
    pass


class HabitLimitError(ValueError):
    pass


async def list_goals(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(UserGoal.goal_code)
        .where(UserGoal.user_id == user_id)
        .order_by(UserGoal.created_at, UserGoal.goal_code)
    )
    return list(rows.scalars())


async def set_goals(session: AsyncSession, user_id: uuid.UUID, codes: list[str]) -> list[str]:
    if len(codes) > MAX_GOALS:
        raise GoalsError(f"at most {MAX_GOALS} goals")
    if len(set(codes)) != len(codes):
        raise GoalsError("duplicate goals")
    unknown = [c for c in codes if c not in GOAL_CODES]
    if unknown:
        raise GoalsError("unknown goal: " + ", ".join(unknown))
    await session.execute(delete(UserGoal).where(UserGoal.user_id == user_id))
    now = datetime.now(UTC)
    session.add_all(UserGoal(user_id=user_id, goal_code=c, created_at=now) for c in codes)
    return codes


async def list_habits(session: AsyncSession, user_id: uuid.UUID) -> list[UserHabit]:
    rows = await session.execute(
        select(UserHabit)
        .where(UserHabit.user_id == user_id, UserHabit.archived_at.is_(None))
        .order_by(UserHabit.created_at, UserHabit.id)
    )
    return list(rows.scalars())


async def add_habit(
    session: AsyncSession, user_id: uuid.UUID, direction: Direction, text: str
) -> UserHabit:
    """Store the habit exactly as the user worded it; the app does not judge it."""
    if len(await list_habits(session, user_id)) >= MAX_HABITS:
        raise HabitLimitError(f"at most {MAX_HABITS} habits")
    habit = UserHabit(user_id=user_id, direction=direction, text=text.strip())
    session.add(habit)
    await session.flush()
    return habit


async def delete_habit(session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(UserHabit)
        .where(UserHabit.id == habit_id, UserHabit.user_id == user_id)
        .returning(UserHabit.id)
    )
    return result.first() is not None
