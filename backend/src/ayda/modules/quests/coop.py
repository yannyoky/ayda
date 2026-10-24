"""Co-op quests at a distance (US-18): storage, joining and the co-op bonus.

The owner turns a taken quest of today into a co-op and invites friends (friendship is
checked by the application layer). Each one who accepts gets the same quest in their own
day. Once everyone who joined (at least two people) has completed it, each of them gets
`coop_bonus_share` of their quest points as a separate ledger row.

Locks: the user's day pool first, then the co-op row, as in completing a quest.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.quests import plans
from ayda.modules.quests.day_service import (
    DayError,
    NewQuest,
    ensure_pool,
    new_day_quest,
    quest_for_update,
    taken_count,
)
from ayda.modules.quests.days import week_start
from ayda.modules.quests.models import (
    Coop,
    CoopPart,
    CoopParticipant,
    DayQuest,
    PointsEntry,
)
from ayda.modules.quests.scoring import scoring_config

JOINED = ("owner", "accepted")


@dataclass(frozen=True)
class Participant:
    user_id: uuid.UUID
    status: str
    day_quest_id: uuid.UUID | None
    completed: bool


async def create_coop(
    session: AsyncSession,
    owner_id: uuid.UUID,
    quest_id: uuid.UUID,
    friend_ids: Sequence[uuid.UUID],
    day: date,
    now: datetime,
) -> Coop:
    _, quest = await quest_for_update(session, owner_id, quest_id, day)
    if quest.state == "completed":
        raise DayError("quest-already-completed")
    if quest.state != "taken":
        raise DayError("quest-not-taken")
    if now >= quest.expires_at:
        raise DayError("quest-expired")
    taken = await session.scalar(
        select(CoopParticipant.coop_id).where(CoopParticipant.day_quest_id == quest.id)
    )
    if taken is not None or quest.source == "coop":
        raise DayError("quest-already-coop")
    coop = Coop(
        id=uuid7(),
        owner_id=owner_id,
        title=quest.title,
        description=quest.description,
        category=quest.category,
        duration_min=quest.duration_min,
        outdoor=quest.outdoor,
        expires_at=quest.expires_at,
        created_at=now,
    )
    session.add(coop)
    await session.flush()
    session.add(
        CoopParticipant(
            coop_id=coop.id,
            user_id=owner_id,
            status="owner",
            day_quest_id=quest.id,
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
    return coop


async def get_coop(session: AsyncSession, coop_id: uuid.UUID) -> Coop | None:
    return await session.get(Coop, coop_id)


async def participant(
    session: AsyncSession, coop_id: uuid.UUID, user_id: uuid.UUID
) -> CoopParticipant | None:
    return await session.get(CoopParticipant, (coop_id, user_id), populate_existing=True)


async def participants(
    session: AsyncSession, coop_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Participant]]:
    """Everyone invited, the owner first, with whether their quest is completed."""
    rows = await session.execute(
        select(
            CoopParticipant.coop_id,
            CoopParticipant.user_id,
            CoopParticipant.status,
            CoopParticipant.day_quest_id,
            DayQuest.state,
        )
        .outerjoin(DayQuest, DayQuest.id == CoopParticipant.day_quest_id)
        .where(CoopParticipant.coop_id.in_(coop_ids))
        .order_by(
            case((CoopParticipant.status == "owner", 0), else_=1),
            CoopParticipant.invited_at,
            CoopParticipant.user_id,
        )
    )
    out: dict[uuid.UUID, list[Participant]] = {c: [] for c in coop_ids}
    for coop_id, user_id, status, day_quest_id, state in rows:
        out[coop_id].append(Participant(user_id, status, day_quest_id, state == "completed"))
    # In a co-op of parts, a person is done when all the parts they hold are done.
    done = await plans.part_completers(session, coop_ids)
    return {
        coop_id: [
            Participant(p.user_id, p.status, p.day_quest_id, done[coop_id].get(p.user_id, False))
            if coop_id in done
            else p
            for p in people
        ]
        for coop_id, people in out.items()
    }


def bonus_awarded(people: Sequence[Participant]) -> bool:
    joined = [p for p in people if p.status in JOINED]
    return len(joined) >= 2 and all(p.completed for p in joined)


async def user_coops(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[tuple[Coop, CoopParticipant]]:
    """Co-ops that are not over for the user: an open invitation until the owner's day
    ends, a joined one until the user's own quest expires. Invitations first."""
    rows = await session.execute(
        select(Coop, CoopParticipant)
        .join(CoopParticipant, CoopParticipant.coop_id == Coop.id)
        .outerjoin(DayQuest, DayQuest.id == CoopParticipant.day_quest_id)
        .where(
            CoopParticipant.user_id == user_id,
            CoopParticipant.status != "declined",
            (Coop.expires_at > now) | (DayQuest.expires_at > now),
        )
        .order_by(
            case((CoopParticipant.status == "invited", 0), else_=1),
            Coop.created_at.desc(),
        )
    )
    return [(c, p) for c, p in rows]


async def _lock(session: AsyncSession, coop_id: uuid.UUID) -> Coop | None:
    return await session.get(Coop, coop_id, with_for_update=True, populate_existing=True)


async def lock_coop(session: AsyncSession, coop_id: uuid.UUID) -> Coop | None:
    """The co-op row locked for this transaction (after the user's day pool, if any)."""
    return await _lock(session, coop_id)


async def accept(
    session: AsyncSession,
    coop_id: uuid.UUID,
    user_id: uuid.UUID,
    day: date,
    expires_at: datetime,
    now: datetime,
) -> tuple[Coop, DayQuest | None]:
    """Join: the quest is added to the user's day as taken (it counts toward the limit).
    A co-op of parts adds none: the user gets the quests of their parts that are open, and
    later ones as the parts open."""
    pool = await ensure_pool(session, user_id, day, now)
    coop = await _lock(session, coop_id)
    me = await participant(session, coop_id, user_id) if coop else None
    if coop is None or me is None:
        raise DayError("coop-not-found")
    if me.status != "invited":
        raise DayError("coop-already-answered")
    if now >= coop.expires_at:
        raise DayError("coop-over")
    if coop.kind == "parts":
        me.status = "accepted"
        me.answered_at = now
        await session.flush()
        await plans.issue_missing(session, coop, user_id, (day, expires_at), now)
        return coop, None
    if await taken_count(session, pool.id) >= scoring_config().max_taken_per_day:
        raise DayError("daily-limit-reached")
    position = await session.scalar(
        select(func.coalesce(func.max(DayQuest.position), -1)).where(DayQuest.pool_id == pool.id)
    )
    quest = new_day_quest(
        pool,
        NewQuest(
            source="coop",
            title=coop.title,
            category=coop.category,
            duration_min=coop.duration_min,
            outdoor=coop.outdoor,
            description=coop.description,
        ),
        (position or 0) + 1,
        "taken",
        expires_at,
        now,
    )
    session.add(quest)
    await session.flush()
    me.status = "accepted"
    me.day_quest_id = quest.id
    me.answered_at = now
    await session.flush()
    return coop, quest


async def decline(
    session: AsyncSession,
    coop_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime,
    slots_for: plans.SlotsFor | None = None,
) -> tuple[Coop, dict[uuid.UUID, int]]:
    """Returns the co-op and the bonuses this made due (the rest may all be done). In a
    co-op of parts the parts of the one who declines go back to the owner."""
    coop = await _lock(session, coop_id)
    me = await participant(session, coop_id, user_id) if coop else None
    if coop is None or me is None:
        raise DayError("coop-not-found")
    if me.status != "invited":
        raise DayError("coop-already-answered")
    me.status = "declined"
    me.answered_at = now
    await session.flush()
    if coop.kind == "parts":
        await plans.reassign_to_owner(session, coop, user_id, slots_for, now)
        return coop, {}
    return coop, await _award_bonus(session, coop, now)


async def after_completion(
    session: AsyncSession,
    quest: DayQuest,
    now: datetime,
    slots_for: plans.SlotsFor | None = None,
) -> plans.Progress | None:
    """Call after the quest is completed (its day pool is locked). Returns the co-op and
    what this changed (the bonuses awarded, by day quest id, and for a part the parts it
    opened), or None if the quest is not in a co-op."""
    part_id = await session.scalar(select(CoopPart.id).where(CoopPart.day_quest_id == quest.id))
    if part_id is not None:
        coop_id = await session.scalar(select(CoopPart.coop_id).where(CoopPart.id == part_id))
        coop = await _lock(session, coop_id) if coop_id else None
        part = await session.get(CoopPart, part_id, populate_existing=True)
        if coop is None or part is None or part.day_quest_id != quest.id or part.state != "open":
            return None
        return await plans.complete_part(session, coop, part, slots_for, now)
    coop_id = await session.scalar(
        select(CoopParticipant.coop_id).where(CoopParticipant.day_quest_id == quest.id)
    )
    if coop_id is None:
        return None
    coop = await _lock(session, coop_id)
    if coop is None:
        return None
    return plans.Progress(coop, await _award_bonus(session, coop, now))


async def _award_bonus(session: AsyncSession, coop: Coop, now: datetime) -> dict[uuid.UUID, int]:
    """With the co-op locked: if everyone who joined has completed, add the bonus rows that
    are missing (a late joiner gets theirs when they complete)."""
    people = (await participants(session, [coop.id]))[coop.id]
    if not bonus_awarded(people):
        return {}
    quest_ids = [p.day_quest_id for p in people if p.status in JOINED and p.day_quest_id]
    rows = await session.execute(
        select(PointsEntry.day_quest_id, PointsEntry.kind, PointsEntry.points).where(
            PointsEntry.day_quest_id.in_(quest_ids)
        )
    )
    earned: dict[uuid.UUID, int] = {}
    has_bonus: set[uuid.UUID] = set()
    for day_quest_id, kind, points in rows:
        if kind == "coop_bonus":
            has_bonus.add(day_quest_id)
        else:
            earned[day_quest_id] = points
    quests = {
        q.id: q for q in await session.scalars(select(DayQuest).where(DayQuest.id.in_(quest_ids)))
    }
    config = scoring_config()
    awarded: dict[uuid.UUID, int] = {}
    for quest_id in quest_ids:
        if quest_id in has_bonus or quest_id not in earned:
            continue
        quest = quests[quest_id]
        points = int(earned[quest_id] * config.coop_bonus_share + 0.5)
        result = await session.execute(
            insert(PointsEntry)
            .values(
                user_id=quest.user_id,
                day_quest_id=quest.id,
                kind="coop_bonus",
                local_date=quest.local_date,
                week_start=week_start(quest.local_date),
                points=points,
                breakdown={
                    "coop_id": str(coop.id),
                    "quest_points": earned[quest_id],
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
    if awarded and coop.bonus_awarded_at is None:
        coop.bonus_awarded_at = now
    await session.flush()
    return awarded


async def coops_by_quest(
    session: AsyncSession, quest_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    if not quest_ids:
        return {}
    rows = await session.execute(
        select(CoopParticipant.day_quest_id, CoopParticipant.coop_id).where(
            CoopParticipant.day_quest_id.in_(quest_ids)
        )
    )
    found = {q: c for q, c in rows if q is not None}
    return found | await plans.part_quest_ids(session, quest_ids)


async def coop_titles(session: AsyncSession, coop_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not coop_ids:
        return {}
    rows = await session.execute(select(Coop.id, Coop.title).where(Coop.id.in_(coop_ids)))
    return {i: t for i, t in rows}


async def coop_ends(
    session: AsyncSession, coop_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """When each co-op is over."""
    if not coop_ids:
        return {}
    rows = await session.execute(select(Coop.id, Coop.expires_at).where(Coop.id.in_(coop_ids)))
    return {i: e for i, e in rows}


async def ended_before(session: AsyncSession, cutoff: datetime) -> list[uuid.UUID]:
    """Co-ops over before `cutoff`."""
    return list(await session.scalars(select(Coop.id).where(Coop.expires_at < cutoff)))
