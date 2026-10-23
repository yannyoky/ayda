"""Shared plans (M5, ADR 0010): co-ops made of parts with their own assignee, place, time,
checklist and order, and the hand-off of a part to a friend.

A part's day quest is created when the part opens and its assignee has joined; it is exempt
from the limit of taken quests, so it needs no lock on the assignee's day pool. The locks
keep the order of ADR 0007: the pool of the user who completes (or hands off), then the
co-op row. Nothing here takes the pool of a second user after the co-op row.
"""

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.quests.day_service import (
    DayError,
    NewQuest,
    add_own_quest,
    ensure_pool,
    get_pool,
    new_day_quest,
)
from ayda.modules.quests.days import week_start
from ayda.modules.quests.models import (
    Coop,
    CoopHandoff,
    CoopPart,
    CoopParticipant,
    CoopPartItem,
    DayQuest,
    PointsEntry,
)
from ayda.modules.quests.scoring import scoring_config

JOINED = ("owner", "accepted")
MAX_JOINED = 4  # the owner and up to 3 friends

# A user's local day and when it ends; the app layer knows the time zones.
Slot = tuple[date, datetime]
SlotsFor = Callable[[Sequence[uuid.UUID]], Awaitable[Mapping[uuid.UUID, Slot]]]


@dataclass(frozen=True)
class PartSpec:
    title: str
    category: str
    duration_min: int
    assignee_id: uuid.UUID
    place: dict[str, Any] | None = None
    starts_at: datetime | None = None
    # Index of an earlier part in the plan that must be done first
    opens_after: int | None = None
    items: Sequence[str] = ()


@dataclass(frozen=True)
class PlanSpec:
    title: str
    category: str
    duration_min: int
    description: str | None = None
    outdoor: bool = False
    place: dict[str, Any] | None = None
    starts_at: datetime | None = None
    # Empty for a `same` co-op
    parts: Sequence[PartSpec] = ()


@dataclass
class Progress:
    """What completing a part changed, for events and notices."""

    coop: Coop
    bonuses: dict[uuid.UUID, int] = field(default_factory=lambda: {})
    completed_part_id: uuid.UUID | None = None
    opened_part_ids: list[uuid.UUID] = field(default_factory=lambda: [])


@dataclass(frozen=True)
class PartView:
    part: CoopPart
    items: list[CoopPartItem]
    handoff: CoopHandoff | None


async def create_plan(
    session: AsyncSession,
    owner_id: uuid.UUID,
    spec: PlanSpec,
    friend_ids: Sequence[uuid.UUID],
    slot: Slot,
    now: datetime,
) -> Coop:
    """A co-op the owner writes directly (no quest to start from). A `same` co-op gives the
    owner its quest as taken, counting toward the limit; a `parts` co-op opens the parts
    that wait for nobody and gives the owner the quests of those assigned to them."""
    day, expires_at = slot
    coop = Coop(
        id=uuid7(),
        owner_id=owner_id,
        title=spec.title,
        description=spec.description,
        category=spec.category,
        duration_min=spec.duration_min,
        outdoor=spec.outdoor,
        kind="parts" if spec.parts else "same",
        place=spec.place,
        starts_at=spec.starts_at,
        expires_at=expires_at,
        created_at=now,
    )
    session.add(coop)
    await session.flush()
    own_quest_id: uuid.UUID | None = None
    if not spec.parts:
        quest = await add_own_quest(
            session,
            owner_id,
            day,
            NewQuest(
                source="coop",
                title=spec.title,
                category=spec.category,
                duration_min=spec.duration_min,
                outdoor=spec.outdoor,
                description=spec.description,
            ),
            expires_at,
            now,
        )
        own_quest_id = quest.id
    session.add(
        CoopParticipant(
            coop_id=coop.id,
            user_id=owner_id,
            status="owner",
            day_quest_id=own_quest_id,
            invited_at=now,
            answered_at=now,
        )
    )
    session.add_all(
        CoopParticipant(coop_id=coop.id, user_id=friend_id, status="invited", invited_at=now)
        for friend_id in dict.fromkeys(friend_ids)
        if friend_id != owner_id
    )
    await session.flush()
    ids = [uuid7() for _ in spec.parts]
    for i, part in enumerate(spec.parts):
        after = ids[part.opens_after] if part.opens_after is not None else None
        session.add(
            CoopPart(
                id=ids[i],
                coop_id=coop.id,
                position=i,
                title=part.title,
                category=part.category,
                duration_min=part.duration_min,
                place=part.place,
                starts_at=part.starts_at,
                assignee_id=part.assignee_id,
                opens_after_part_id=after,
                state="locked" if after else "open",
                day_quest_id=None,
            )
        )
        await session.flush()
        session.add_all(
            CoopPartItem(id=uuid7(), part_id=ids[i], position=n, text=text, done=False)
            for n, text in enumerate(part.items)
        )
    await session.flush()
    if spec.parts:
        await issue_missing(session, coop, owner_id, slot, now)
    return coop


async def parts_of(
    session: AsyncSession, coop_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[PartView]]:
    """Parts in order, each with its checklist and pending hand-off."""
    out: dict[uuid.UUID, list[PartView]] = {c: [] for c in coop_ids}
    if not coop_ids:
        return out
    parts = list(
        await session.scalars(
            select(CoopPart)
            .where(CoopPart.coop_id.in_(coop_ids))
            .order_by(CoopPart.coop_id, CoopPart.position)
        )
    )
    part_ids = [p.id for p in parts]
    items: dict[uuid.UUID, list[CoopPartItem]] = {p.id: [] for p in parts}
    for item in await session.scalars(
        select(CoopPartItem)
        .where(CoopPartItem.part_id.in_(part_ids))
        .order_by(CoopPartItem.part_id, CoopPartItem.position)
    ):
        items[item.part_id].append(item)
    handoffs = {
        h.part_id: h
        for h in await session.scalars(select(CoopHandoff).where(CoopHandoff.part_id.in_(part_ids)))
    }
    for p in parts:
        out[p.coop_id].append(PartView(p, items[p.id], handoffs.get(p.id)))
    return out


async def part_completers(
    session: AsyncSession, coop_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[uuid.UUID, bool]]:
    """For `parts` co-ops: per user with a part, whether all their parts are done."""
    out: dict[uuid.UUID, dict[uuid.UUID, bool]] = {}
    if not coop_ids:
        return out
    rows = await session.execute(
        select(CoopPart.coop_id, CoopPart.assignee_id, CoopPart.state).where(
            CoopPart.coop_id.in_(coop_ids)
        )
    )
    for coop_id, user_id, state in rows:
        users = out.setdefault(coop_id, {})
        users[user_id] = users.get(user_id, True) and state == "done"
    return out


async def handoff_recipients(session: AsyncSession, coop_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(CoopHandoff.to_user_id)
        .join(CoopPart, CoopPart.id == CoopHandoff.part_id)
        .where(CoopPart.coop_id == coop_id)
    )
    return list(dict.fromkeys(rows))


async def has_pending_handoff(
    session: AsyncSession, coop_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    found = await session.scalar(
        select(CoopHandoff.part_id)
        .join(CoopPart, CoopPart.id == CoopHandoff.part_id)
        .where(CoopPart.coop_id == coop_id, CoopHandoff.to_user_id == user_id)
        .limit(1)
    )
    return found is not None


async def part_quest_ids(
    session: AsyncSession, quest_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Day quest id -> co-op id, for quests that belong to a part."""
    if not quest_ids:
        return {}
    rows = await session.execute(
        select(CoopPart.day_quest_id, CoopPart.coop_id).where(CoopPart.day_quest_id.in_(quest_ids))
    )
    return {q: c for q, c in rows if q is not None}


async def quest_owners(
    session: AsyncSession, quest_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    rows = await session.execute(
        select(DayQuest.id, DayQuest.user_id).where(DayQuest.id.in_(quest_ids))
    )
    return {q: u for q, u in rows}


async def _joined(session: AsyncSession, coop_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(CoopParticipant.user_id).where(
            CoopParticipant.coop_id == coop_id, CoopParticipant.status.in_(JOINED)
        )
    )
    return set(rows)


async def _issue_quest(
    session: AsyncSession, coop: Coop, part: CoopPart, slot: Slot, now: datetime
) -> DayQuest:
    """The assignee's day quest for an open part: taken, outside the daily limit."""
    day, expires_at = slot
    pool = await ensure_pool(session, part.assignee_id, day, now, lock=False)
    position = await session.scalar(
        select(func.coalesce(func.max(DayQuest.position), -1)).where(DayQuest.pool_id == pool.id)
    )
    quest = new_day_quest(
        pool,
        NewQuest(
            source="coop",
            title=part.title,
            category=part.category,
            duration_min=part.duration_min,
            outdoor=coop.outdoor,
            description=coop.title,
        ),
        (position or 0) + 1,
        "taken",
        expires_at,
        now,
    )
    session.add(quest)
    await session.flush()
    part.day_quest_id = quest.id
    return quest


async def issue_missing(
    session: AsyncSession, coop: Coop, user_id: uuid.UUID, slot: Slot, now: datetime
) -> list[DayQuest]:
    """Quests for the open parts assigned to a user who has joined and has none yet."""
    parts = await session.scalars(
        select(CoopPart)
        .where(
            CoopPart.coop_id == coop.id,
            CoopPart.assignee_id == user_id,
            CoopPart.state == "open",
            CoopPart.day_quest_id.is_(None),
        )
        .order_by(CoopPart.position)
    )
    return [await _issue_quest(session, coop, part, slot, now) for part in parts]


async def reassign_to_owner(
    session: AsyncSession, coop: Coop, user_id: uuid.UUID, slots_for: SlotsFor | None, now: datetime
) -> None:
    """A friend declined: their parts go back to the owner (who gets the open ones)."""
    parts = list(
        await session.scalars(
            select(CoopPart).where(CoopPart.coop_id == coop.id, CoopPart.assignee_id == user_id)
        )
    )
    if not parts:
        return
    await session.execute(delete(CoopHandoff).where(CoopHandoff.part_id.in_([p.id for p in parts])))
    for part in parts:
        part.assignee_id = coop.owner_id
    await session.flush()
    if slots_for is not None and any(p.state == "open" for p in parts):
        slots = await slots_for([coop.owner_id])
        if coop.owner_id in slots:
            await issue_missing(session, coop, coop.owner_id, slots[coop.owner_id], now)


async def complete_part(
    session: AsyncSession,
    coop: Coop,
    part: CoopPart,
    slots_for: SlotsFor | None,
    now: datetime,
) -> Progress:
    """With the co-op locked: mark the part done, open the parts that waited for it and
    award the bonus once every part is done."""
    part.state = "done"
    part.completed_at = now
    await session.execute(delete(CoopHandoff).where(CoopHandoff.part_id == part.id))
    waiting = list(
        await session.scalars(
            select(CoopPart)
            .where(CoopPart.opens_after_part_id == part.id, CoopPart.state == "locked")
            .order_by(CoopPart.position)
        )
    )
    joined = await _joined(session, coop.id)
    ready = [p for p in waiting if p.assignee_id in joined]
    slots: Mapping[uuid.UUID, Slot] = {}
    if ready and slots_for is not None:
        slots = await slots_for(list(dict.fromkeys(p.assignee_id for p in ready)))
    for p in waiting:
        p.state = "open"
        if p.assignee_id in slots:
            await _issue_quest(session, coop, p, slots[p.assignee_id], now)
    await session.flush()
    return Progress(
        coop,
        await _award_bonus(session, coop, now),
        completed_part_id=part.id,
        opened_part_ids=[p.id for p in waiting],
    )


async def _award_bonus(session: AsyncSession, coop: Coop, now: datetime) -> dict[uuid.UUID, int]:
    """With the co-op locked: when every part is done before the day ends, each user who did
    a part gets one bonus row, attached to their first part quest."""
    if coop.bonus_awarded_at is not None or now >= coop.expires_at:
        return {}
    parts = list(
        await session.scalars(
            select(CoopPart).where(CoopPart.coop_id == coop.id).order_by(CoopPart.position)
        )
    )
    if not parts or any(p.state != "done" or p.day_quest_id is None for p in parts):
        return {}
    quest_ids = [p.day_quest_id for p in parts if p.day_quest_id]
    owners = await quest_owners(session, quest_ids)
    rows = await session.execute(
        select(PointsEntry.day_quest_id, PointsEntry.points).where(
            PointsEntry.day_quest_id.in_(quest_ids), PointsEntry.kind == "quest"
        )
    )
    earned = {quest_id: points for quest_id, points in rows}
    quests = {
        q.id: q for q in await session.scalars(select(DayQuest).where(DayQuest.id.in_(quest_ids)))
    }
    first: dict[uuid.UUID, uuid.UUID] = {}
    total: dict[uuid.UUID, int] = {}
    for quest_id in quest_ids:
        if quest_id not in earned:
            continue
        user_id = owners[quest_id]
        first.setdefault(user_id, quest_id)
        total[user_id] = total.get(user_id, 0) + earned[quest_id]
    config = scoring_config()
    awarded: dict[uuid.UUID, int] = {}
    for user_id, quest_id in first.items():
        quest = quests[quest_id]
        points = int(total[user_id] * config.coop_bonus_share + 0.5)
        result = await session.execute(
            insert(PointsEntry)
            .values(
                user_id=user_id,
                day_quest_id=quest_id,
                kind="coop_bonus",
                local_date=quest.local_date,
                week_start=week_start(quest.local_date),
                points=points,
                breakdown={
                    "coop_id": str(coop.id),
                    "quest_points": total[user_id],
                    "share": config.coop_bonus_share,
                    "config_version": config.version,
                },
                created_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_points_ledger_day_quest_id_kind")
            .returning(PointsEntry.id)
        )
        if result.scalar_one_or_none() is not None:
            awarded[quest_id] = points
    if awarded:
        coop.bonus_awarded_at = now
    await session.flush()
    return awarded


async def tick_item(
    session: AsyncSession,
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
    done: bool,
    now: datetime,
) -> Coop:
    """The assignee ticks or unticks a checklist item of a part that is not locked."""
    part = await session.get(CoopPart, part_id, populate_existing=True)
    item = await session.get(CoopPartItem, item_id, populate_existing=True)
    coop = await session.get(Coop, coop_id)
    if part is None or coop is None or part.coop_id != coop_id:
        raise DayError("part-not-found")
    if item is None or item.part_id != part_id:
        raise DayError("item-not-found")
    if part.assignee_id != user_id:
        raise DayError("not-part-assignee")
    if part.state == "locked":
        raise DayError("part-locked")
    item.done = done
    item.done_at = now if done else None
    await session.flush()
    return coop


async def _part_in(session: AsyncSession, coop_id: uuid.UUID, part_id: uuid.UUID) -> CoopPart:
    part = await session.get(CoopPart, part_id, populate_existing=True)
    if part is None or part.coop_id != coop_id:
        raise DayError("part-not-found")
    return part


async def offer_handoff(
    session: AsyncSession,
    coop: Coop,
    part_id: uuid.UUID,
    user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    now: datetime,
) -> CoopHandoff:
    """With the co-op locked. The friend's friendship with the assignee is checked by the
    application layer."""
    part = await _part_in(session, coop.id, part_id)
    if part.assignee_id != user_id:
        raise DayError("not-part-assignee")
    if now >= coop.expires_at:
        raise DayError("coop-over")
    if part.state == "done":
        raise DayError("part-done")
    if to_user_id == user_id:
        raise DayError("handoff-to-self")
    if await session.get(CoopHandoff, part_id, populate_existing=True) is not None:
        raise DayError("handoff-pending")
    handoff = CoopHandoff(
        part_id=part_id, from_user_id=user_id, to_user_id=to_user_id, created_at=now
    )
    session.add(handoff)
    await session.flush()
    return handoff


async def withdraw_handoff(
    session: AsyncSession, coop: Coop, part_id: uuid.UUID, user_id: uuid.UUID
) -> CoopHandoff:
    part = await _part_in(session, coop.id, part_id)
    handoff = await session.get(CoopHandoff, part_id, populate_existing=True)
    if part.assignee_id != user_id:
        raise DayError("not-part-assignee")
    if handoff is None:
        raise DayError("handoff-not-found")
    await session.delete(handoff)
    await session.flush()
    return handoff


async def lock_for_handoff(
    session: AsyncSession, coop_id: uuid.UUID, part_id: uuid.UUID
) -> Coop | None:
    """The first lock of accepting a hand-off: the pool of the assignee who completes the
    part (the order of ADR 0007), then the co-op row. None if there is no such part."""
    part = await session.get(CoopPart, part_id, populate_existing=True)
    if part is None or part.coop_id != coop_id:
        return None
    if part.day_quest_id is not None:
        quest = await session.get(DayQuest, part.day_quest_id, populate_existing=True)
        if quest is not None:
            await get_pool(session, quest.user_id, quest.local_date, lock=True)
    return await session.get(Coop, coop_id, with_for_update=True, populate_existing=True)


async def accept_handoff(
    session: AsyncSession,
    coop: Coop,
    part_id: uuid.UUID,
    user_id: uuid.UUID,
    slot: Slot,
    now: datetime,
) -> uuid.UUID:
    """With the pool and the co-op locked by `lock_for_handoff`. The friend joins the
    co-op, takes the part, and an open part moves its quest to them. Returns the previous
    assignee."""
    part = await _part_in(session, coop.id, part_id)
    handoff = await session.get(CoopHandoff, part_id, populate_existing=True)
    if handoff is None or handoff.to_user_id != user_id:
        raise DayError("handoff-not-found")
    if now >= coop.expires_at:
        raise DayError("coop-over")
    me = await session.get(CoopParticipant, (coop.id, user_id), populate_existing=True)
    if me is None or me.status not in JOINED:
        if len(await _joined(session, coop.id)) >= MAX_JOINED:
            raise DayError("coop-full")
        if me is None:
            session.add(
                CoopParticipant(
                    coop_id=coop.id,
                    user_id=user_id,
                    status="accepted",
                    invited_at=now,
                    answered_at=now,
                )
            )
        else:
            me.status = "accepted"
            me.answered_at = now
    previous = part.assignee_id
    old_quest = (
        await session.get(DayQuest, part.day_quest_id, populate_existing=True)
        if part.day_quest_id
        else None
    )
    if old_quest is not None and old_quest.state == "taken":
        old_quest.state = "replaced"
    part.day_quest_id = None
    part.assignee_id = user_id
    await session.delete(handoff)
    await session.flush()
    await issue_missing(session, coop, user_id, slot, now)
    return previous


async def decline_handoff(
    session: AsyncSession, coop: Coop, part_id: uuid.UUID, user_id: uuid.UUID
) -> CoopHandoff:
    await _part_in(session, coop.id, part_id)
    handoff = await session.get(CoopHandoff, part_id, populate_existing=True)
    if handoff is None or handoff.to_user_id != user_id:
        raise DayError("handoff-not-found")
    await session.delete(handoff)
    await session.flush()
    return handoff


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Hand-offs of the user go; parts assigned to them return to the owner. (A part that was
    open loses its quest with the user's day; the plan ends with the owner's day anyway.)"""
    await session.execute(
        delete(CoopHandoff).where(
            (CoopHandoff.from_user_id == user_id) | (CoopHandoff.to_user_id == user_id)
        )
    )
    await session.execute(
        update(CoopPart)
        .where(
            CoopPart.assignee_id == user_id,
            CoopPart.coop_id.in_(select(Coop.id).where(Coop.owner_id != user_id)),
        )
        .values(
            assignee_id=select(Coop.owner_id).where(Coop.id == CoopPart.coop_id).scalar_subquery()
        )
    )
