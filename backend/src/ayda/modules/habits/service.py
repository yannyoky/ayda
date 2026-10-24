import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.habits.interests import (
    INTEREST_CODES,
    MAX_INTERESTS,
    MAX_TAG_LENGTH,
    MAX_TAGS,
)
from ayda.modules.habits.models import UserHabit, UserInterest, UserInterestTag

Direction = Literal["more", "less"]
MAX_HABITS = 20


class InterestsError(ValueError):
    pass


class HabitLimitError(ValueError):
    pass


def normalize_tag(tag: str) -> str:
    """Lower case, spaces collapsed; the tag is only ever matched against event titles."""
    return " ".join(tag.lower().replace("ё", "е").split())


async def list_interests(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(UserInterest.code)
        .where(UserInterest.user_id == user_id)
        .order_by(UserInterest.created_at, UserInterest.code)
    )
    return list(rows.scalars())


async def list_tags(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(UserInterestTag.tag)
        .where(UserInterestTag.user_id == user_id)
        .order_by(UserInterestTag.created_at, UserInterestTag.tag)
    )
    return list(rows.scalars())


async def set_interests(
    session: AsyncSession, user_id: uuid.UUID, codes: list[str], tags: list[str]
) -> tuple[list[str], list[str]]:
    """Replace the user's interests: catalog codes and their own words."""
    if len(codes) > MAX_INTERESTS:
        raise InterestsError(f"at most {MAX_INTERESTS} interests")
    if len(set(codes)) != len(codes):
        raise InterestsError("duplicate interests")
    unknown = [c for c in codes if c not in INTEREST_CODES]
    if unknown:
        raise InterestsError("unknown interest: " + ", ".join(unknown))
    clean = list(dict.fromkeys(t for t in (normalize_tag(t) for t in tags) if t))
    if len(clean) > MAX_TAGS:
        raise InterestsError(f"at most {MAX_TAGS} own interests")
    if any(len(t) > MAX_TAG_LENGTH or "http" in t or "@" in t for t in clean):
        raise InterestsError("an own interest is a short word or two")
    await session.execute(delete(UserInterest).where(UserInterest.user_id == user_id))
    await session.execute(delete(UserInterestTag).where(UserInterestTag.user_id == user_id))
    now = datetime.now(UTC)
    session.add_all(UserInterest(user_id=user_id, code=c, created_at=now) for c in codes)
    session.add_all(UserInterestTag(user_id=user_id, tag=t, created_at=now) for t in clean)
    return codes, clean


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
