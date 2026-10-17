"""Check-ins, daily pools and day quests: storage and the daily limits."""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.quests.models import Checkin, DayPool, DayQuest, Template
from ayda.modules.quests.scoring import scoring_config
from ayda.modules.quests.selection import CODE_WHY, pick_alternative

MAX_CHECKINS_PER_DAY = 10
ACTIVE_STATES = ("taken", "completed")


# Finds another event for a replaced event quest, skipping the given listing ids.
EventPicker = Callable[[DayPool, set[int]], Awaitable["NewQuest | None"]]


class DayError(Exception):
    """A rule of the day was broken; `code` becomes the problem code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NewQuest:
    source: str
    title: str
    category: str
    duration_min: int
    outdoor: bool = False
    template_id: int | None = None
    description: str | None = None
    why: str | None = None
    event_id: int | None = None
    event: dict[str, Any] | None = None


def quest_from_template(template: Template, why: str | None = None) -> NewQuest:
    return NewQuest(
        source="catalog",
        title=template.title,
        category=template.category,
        duration_min=template.duration_min,
        outdoor=template.outdoor,
        template_id=template.id,
        description=template.description,
        why=why,
    )


async def active_templates(session: AsyncSession) -> list[Template]:
    rows = await session.scalars(select(Template).where(Template.active).order_by(Template.id))
    return list(rows)


async def get_checkin(session: AsyncSession, user_id: uuid.UUID, day: date) -> Checkin | None:
    return await session.scalar(
        select(Checkin).where(Checkin.user_id == user_id, Checkin.local_date == day)
    )


async def get_pool(
    session: AsyncSession, user_id: uuid.UUID, day: date, *, lock: bool = False
) -> DayPool | None:
    query = select(DayPool).where(DayPool.user_id == user_id, DayPool.local_date == day)
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def ensure_pool(
    session: AsyncSession, user_id: uuid.UUID, day: date, now: datetime
) -> DayPool:
    """Today's pool row, locked for this transaction; created empty (`none`) if missing."""
    await session.execute(
        insert(DayPool)
        .values(
            id=uuid7(),
            user_id=user_id,
            local_date=day,
            status="none",
            context={},
            replacements_used=0,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_day_pools_user_id_local_date")
    )
    pool = await get_pool(session, user_id, day, lock=True)
    assert pool is not None
    await session.refresh(pool)
    return pool


async def day_quests(session: AsyncSession, pool_id: uuid.UUID) -> list[DayQuest]:
    rows = await session.scalars(
        select(DayQuest)
        .where(DayQuest.pool_id == pool_id)
        .order_by(DayQuest.position, DayQuest.created_at)
    )
    return list(rows)


async def excluded_template_ids(session: AsyncSession, user_id: uuid.UUID, day: date) -> set[int]:
    """Catalog quests not to offer: shown yesterday, and replaced, taken or done today."""
    rows = await session.execute(
        select(DayQuest.template_id, DayQuest.local_date, DayQuest.state).where(
            DayQuest.user_id == user_id,
            DayQuest.local_date.in_((day, day - timedelta(days=1))),
            DayQuest.template_id.is_not(None),
        )
    )
    out: set[int] = set()
    for template_id, local_date, state in rows:
        if template_id is not None and (local_date != day or state != "offered"):
            out.add(template_id)
    return out


async def excluded_event_ids(session: AsyncSession, user_id: uuid.UUID, day: date) -> set[int]:
    """Events not to offer again today: replaced, taken or done."""
    rows = await session.scalars(
        select(DayQuest.event_id).where(
            DayQuest.user_id == user_id,
            DayQuest.local_date == day,
            DayQuest.event_id.is_not(None),
            DayQuest.state != "offered",
        )
    )
    return {i for i in rows if i is not None}


async def save_checkin(
    session: AsyncSession,
    user_id: uuid.UUID,
    day: date,
    text: str,
    mood: str,
    parsed: dict[str, Any],
    now: datetime,
) -> tuple[Checkin, bool]:
    """Create or replace today's check-in; returns (checkin, replaced)."""
    checkin = await get_checkin(session, user_id, day)
    if checkin is None:
        checkin = Checkin(
            user_id=user_id,
            local_date=day,
            text=text or None,
            mood=mood,
            parsed=parsed,
            submissions=1,
            created_at=now,
            updated_at=now,
        )
        session.add(checkin)
        await session.flush()
        return checkin, False
    if checkin.submissions >= MAX_CHECKINS_PER_DAY:
        raise DayError("too-many-checkins")
    checkin.text = text or None
    checkin.mood = mood
    checkin.parsed = parsed
    checkin.submissions += 1
    checkin.updated_at = now
    await session.flush()
    return checkin, True


async def rebuild_pool(
    session: AsyncSession,
    pool: DayPool,
    checkin: Checkin,
    quests: Sequence[NewQuest],
    *,
    ranked_by: str,
    provider: str | None,
    weather: dict[str, Any] | None,
    candidate_ids: list[int],
    expires_at: datetime,
    now: datetime,
    event_ids: list[int] | None = None,
) -> list[DayQuest]:
    """Drop quests that were only offered and add the new ones after the kept ones."""
    await session.execute(
        delete(DayQuest).where(DayQuest.pool_id == pool.id, DayQuest.state == "offered")
    )
    kept = await day_quests(session, pool.id)
    start = max((q.position for q in kept), default=-1) + 1
    added = [
        new_day_quest(pool, q, start + i, "offered", expires_at, now) for i, q in enumerate(quests)
    ]
    session.add_all(added)
    pool.checkin_id = checkin.id
    pool.status = "ready" if added or kept else "failed"
    pool.ranked_by = ranked_by
    pool.provider = provider
    pool.weather = weather
    pool.context = {"candidate_ids": candidate_ids, "event_ids": event_ids or []}
    pool.updated_at = now
    await session.flush()
    return added


def new_day_quest(
    pool: DayPool, quest: NewQuest, position: int, state: str, expires_at: datetime, now: datetime
) -> DayQuest:
    return DayQuest(
        id=uuid7(),
        pool_id=pool.id,
        user_id=pool.user_id,
        local_date=pool.local_date,
        source=quest.source,
        template_id=quest.template_id,
        event_id=quest.event_id,
        event=quest.event,
        title=quest.title,
        description=quest.description,
        category=quest.category,
        duration_min=quest.duration_min,
        outdoor=quest.outdoor,
        why=quest.why,
        position=position,
        state=state,
        taken_at=now if state == "taken" else None,
        expires_at=expires_at,
        created_at=now,
    )


async def taken_count(session: AsyncSession, pool_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(DayQuest)
        .where(DayQuest.pool_id == pool_id, DayQuest.state.in_(ACTIVE_STATES))
    )
    return count or 0


async def quest_for_update(
    session: AsyncSession, user_id: uuid.UUID, quest_id: uuid.UUID, day: date
) -> tuple[DayPool, DayQuest]:
    """Lock today's pool first (it serializes the limits), then read the quest."""
    pool = await get_pool(session, user_id, day, lock=True)
    quest = await session.get(DayQuest, quest_id, populate_existing=True)
    if pool is None or quest is None or quest.user_id != user_id or quest.pool_id != pool.id:
        raise DayError("quest-not-found")
    return pool, quest


async def take_quest(
    session: AsyncSession, user_id: uuid.UUID, quest_id: uuid.UUID, day: date, now: datetime
) -> DayQuest:
    pool, quest = await quest_for_update(session, user_id, quest_id, day)
    if quest.state != "offered":
        raise DayError("quest-not-offered")
    if await taken_count(session, pool.id) >= scoring_config().max_taken_per_day:
        raise DayError("daily-limit-reached")
    quest.state = "taken"
    quest.taken_at = now
    await session.flush()
    return quest


async def add_own_quest(
    session: AsyncSession,
    user_id: uuid.UUID,
    day: date,
    quest: NewQuest,
    expires_at: datetime,
    now: datetime,
) -> DayQuest:
    pool = await ensure_pool(session, user_id, day, now)
    if await taken_count(session, pool.id) >= scoring_config().max_taken_per_day:
        raise DayError("daily-limit-reached")
    position = await session.scalar(
        select(func.coalesce(func.max(DayQuest.position), -1)).where(DayQuest.pool_id == pool.id)
    )
    row = new_day_quest(pool, quest, (position or 0) + 1, "taken", expires_at, now)
    session.add(row)
    await session.flush()
    return row


def replacements_left(pool: DayPool | None) -> int:
    used = pool.replacements_used if pool else 0
    return max(scoring_config().max_replacements_per_day - used, 0)


async def replace_quest(
    session: AsyncSession,
    user_id: uuid.UUID,
    quest_id: uuid.UUID,
    reason: str | None,
    day: date,
    now: datetime,
    pick_event: EventPicker | None = None,
) -> tuple[DayQuest, DayQuest | None, DayPool]:
    """Mark an offered quest replaced and offer an alternative from the day's candidates:
    another event for an event quest when `pick_event` finds one, else a catalog quest."""
    pool, quest = await quest_for_update(session, user_id, quest_id, day)
    if quest.state != "offered":
        raise DayError("quest-not-offered")
    if replacements_left(pool) == 0:
        raise DayError("no-replacements-left")

    in_pool_quests = await day_quests(session, pool.id)
    new: NewQuest | None = None
    if quest.source == "event" and pick_event is not None:
        skip = {q.event_id for q in in_pool_quests if q.event_id is not None}
        skip |= await excluded_event_ids(session, user_id, day)
        new = await pick_event(pool, skip)
    if new is None:
        candidate_ids: list[int] = list(pool.context.get("candidate_ids", []))
        in_pool = {q.template_id for q in in_pool_quests if q.template_id}
        excluded = in_pool | await excluded_template_ids(session, user_id, day)
        templates = {
            t.id: t
            for t in await session.scalars(
                select(Template).where(Template.id.in_(candidate_ids), Template.active)
            )
        }
        candidates = [templates[i] for i in candidate_ids if i in templates and i not in excluded]
        alternative = pick_alternative(candidates, quest.category, quest.duration_min)
        if alternative is not None:
            new = quest_from_template(alternative, CODE_WHY.get(alternative.category))

    quest.state = "replaced"
    quest.reject_reason = reason
    pool.replacements_used += 1
    pool.updated_at = now
    replacement: DayQuest | None = None
    if new is not None:
        replacement = new_day_quest(pool, new, quest.position, "offered", quest.expires_at, now)
        session.add(replacement)
        quest.replaced_by_id = replacement.id
    await session.flush()
    return quest, replacement, pool
