"""Points ledger and streaks (docs/prd.md "Quests, points, streaks and ladder").

A day counts for the streak when at least one quest is completed. One missed day a week
(Monday-based) is frozen automatically: the streak goes on as if the day had counted.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.quests.day_service import DayError, get_pool
from ayda.modules.quests.days import week_start
from ayda.modules.quests.models import DayQuest, PointsEntry, Streak
from ayda.modules.quests.scoring import quest_points, scoring_config


@dataclass(frozen=True)
class StreakState:
    current_days: int
    best_days: int
    last_counted_date: date | None
    freeze_week_start: date | None


@dataclass(frozen=True)
class StreakView:
    current_days: int
    best_days: int
    freeze_available: bool


@dataclass(frozen=True)
class Award:
    points: int
    base: int
    visibility_multiplier: float
    streak_multiplier: float
    streak: StreakView


def _freeze_covers(state: StreakState, missed: date) -> bool:
    return state.freeze_week_start != week_start(missed)


def count_day(state: StreakState, day: date) -> StreakState:
    """The streak after a completed quest on `day`."""
    last = state.last_counted_date
    if last is not None and day <= last:
        return state  # already counted (or an older day; streaks never go back)
    freeze = state.freeze_week_start
    if last == day - timedelta(days=1):
        current = state.current_days + 1
    elif last == day - timedelta(days=2) and _freeze_covers(state, day - timedelta(days=1)):
        current = state.current_days + 1
        freeze = week_start(day - timedelta(days=1))
    else:
        current = 1
    return StreakState(current, max(state.best_days, current), day, freeze)


def view(state: StreakState, today: date) -> StreakView:
    """What the user sees today: a streak broken by two missed days, or one missed day
    without a freeze left, shows 0."""
    last = state.last_counted_date
    alive = last is not None and (
        last >= today - timedelta(days=1)
        or (last == today - timedelta(days=2) and _freeze_covers(state, today - timedelta(days=1)))
    )
    return StreakView(
        current_days=state.current_days if alive else 0,
        best_days=state.best_days,
        freeze_available=state.freeze_week_start != week_start(today),
    )


def _state(row: Streak | None) -> StreakState:
    if row is None:
        return StreakState(0, 0, None, None)
    return StreakState(
        row.current_days, row.best_days, row.last_counted_date, row.freeze_week_start
    )


async def streak_view(session: AsyncSession, user_id: uuid.UUID, today: date) -> StreakView:
    return view(_state(await session.get(Streak, user_id)), today)


async def award(session: AsyncSession, quest: DayQuest, visibility: str, now: datetime) -> Award:
    """Count the quest's day for the streak and write its ledger row (once per quest)."""
    await session.execute(
        insert(Streak)
        .values(user_id=quest.user_id, current_days=0, best_days=0, updated_at=now)
        .on_conflict_do_nothing()
    )
    row = await session.get(Streak, quest.user_id, with_for_update=True, populate_existing=True)
    assert row is not None
    state = count_day(_state(row), quest.local_date)
    row.current_days, row.best_days = state.current_days, state.best_days
    row.last_counted_date, row.freeze_week_start = state.last_counted_date, state.freeze_week_start
    row.updated_at = now

    config = scoring_config()
    points, base, vis, streak = quest_points(
        quest.duration_min, visibility, state.current_days, config
    )
    session.add(
        PointsEntry(
            user_id=quest.user_id,
            day_quest_id=quest.id,
            local_date=quest.local_date,
            week_start=week_start(quest.local_date),
            points=points,
            breakdown={
                "base": base,
                "visibility_multiplier": vis,
                "streak_multiplier": streak,
                "streak_days": state.current_days,
                "config_version": config.version,
            },
            created_at=now,
        )
    )
    await session.flush()
    return Award(points, base, vis, streak, view(state, quest.local_date))


async def points_summary(session: AsyncSession, user_id: uuid.UUID, today: date) -> tuple[int, int]:
    """(points today, points this week)."""
    row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(PointsEntry.points).filter(PointsEntry.local_date == today), 0
                ),
                func.coalesce(func.sum(PointsEntry.points), 0),
            ).where(PointsEntry.user_id == user_id, PointsEntry.week_start == week_start(today))
        )
    ).one()
    return int(row[0]), int(row[1])


async def points_by_quest(
    session: AsyncSession, quest_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not quest_ids:
        return {}
    rows = await session.execute(
        select(PointsEntry.day_quest_id, PointsEntry.points).where(
            PointsEntry.day_quest_id.in_(quest_ids)
        )
    )
    return {quest_id: points for quest_id, points in rows}


async def complete_quest(
    session: AsyncSession, user_id: uuid.UUID, quest_id: uuid.UUID, visibility: str, now: datetime
) -> tuple[DayQuest, Award]:
    """Mark a taken quest completed before it expires and award its points."""
    quest = await session.get(DayQuest, quest_id)
    if quest is None or quest.user_id != user_id:
        raise DayError("quest-not-found")
    await get_pool(session, user_id, quest.local_date, lock=True)
    await session.refresh(quest)
    if quest.state == "completed":
        raise DayError("quest-already-completed")
    if quest.state != "taken":
        raise DayError("quest-not-taken")
    if now >= quest.expires_at:
        raise DayError("quest-expired")
    quest.state = "completed"
    quest.visibility = visibility
    quest.completed_at = now
    await session.flush()
    return quest, await award(session, quest, visibility, now)
