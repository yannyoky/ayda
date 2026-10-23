"""Co-op quests at a distance (US-18) across modules: the quest and its bonus (quests),
friendships (social), names (auth), the shared chat (chat), realtime and bot notices."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import (
    Coop,
    CoopCreateInput,
    CoopHandoffOffer,
    CoopItem,
    CoopParticipant,
    CoopStatus,
    Place,
)
from ayda.api.schemas import CoopPart as CoopPartSchema
from ayda.app.day_problems import day_problem
from ayda.app.feed import user_summary
from ayda.app.notifications import RENDERERS, Renderer, app_button, notify
from ayda.app.notifications import Message as BotMessage
from ayda.app.realtime import BUILDERS, Delivery, publish
from ayda.core.config import Settings
from ayda.core.problems import Problem
from ayda.core.realtime import Realtime
from ayda.modules import analytics, auth, chat, quests, social
from ayda.modules.analytics import EventType
from ayda.modules.quests import days as day_clock
from ayda.modules.quests.day_service import DayError

COOP_UPDATED = "coop.updated"
INVITE_KIND = "coop.invite"
BONUS_KIND = "coop.bonus"
HANDOFF_KIND = "coop.handoff"


def _part_schema(
    view: quests.plans.PartView, users: Mapping[uuid.UUID, auth.User], viewer_id: uuid.UUID
) -> CoopPartSchema:
    part = view.part
    handoff = view.handoff
    return CoopPartSchema(
        id=part.id,
        position=part.position,
        title=part.title,
        category=part.category,  # pyright: ignore[reportArgumentType]
        duration_min=part.duration_min,
        place=Place.model_validate(part.place) if part.place else None,
        starts_at=part.starts_at,
        assignee=user_summary(users.get(part.assignee_id), part.assignee_id),
        state=part.state,  # pyright: ignore[reportArgumentType]
        opens_after=part.opens_after_part_id,
        items=[CoopItem(id=i.id, text=i.text, done=i.done) for i in view.items],
        my_quest_id=part.day_quest_id if part.assignee_id == viewer_id else None,
        handoff=CoopHandoffOffer(
            to=user_summary(users.get(handoff.to_user_id), handoff.to_user_id),
            for_me=handoff.to_user_id == viewer_id,
        )
        if handoff
        else None,
    )


async def build_coops(
    session: AsyncSession,
    rows: Sequence[tuple[quests.Coop, quests.CoopParticipant | None]],
    viewer_id: uuid.UUID,
    absent_status: CoopStatus = "invited",
) -> list[Coop]:
    """Co-ops as one viewer sees them; `rows` pair each co-op with the viewer's place. A
    viewer with no place yet (the friend a part is offered to) is shown as `absent_status`."""
    ids = [c.id for c, _ in rows]
    people = await quests.coop.participants(session, ids)
    chats = await chat.conversations_for_coops(session, ids)
    parts = await quests.plans.parts_of(session, ids)
    user_ids = {p.user_id for ps in people.values() for p in ps}
    for views in parts.values():
        for view in views:
            user_ids.add(view.part.assignee_id)
            if view.handoff:
                user_ids.add(view.handoff.to_user_id)
    users = await auth.get_users(session, list(user_ids))
    out: list[Coop] = []
    for coop, me in rows:
        joined = me is not None and me.status in quests.coop.JOINED
        is_parts = coop.kind == "parts"
        out.append(
            Coop(
                id=coop.id,
                title=coop.title,
                category=coop.category,  # pyright: ignore[reportArgumentType]
                duration_min=coop.duration_min,
                owner=user_summary(users.get(coop.owner_id), coop.owner_id),
                my_status=me.status if me else absent_status,  # pyright: ignore[reportArgumentType]
                participants=[
                    CoopParticipant(
                        user=user_summary(users.get(p.user_id), p.user_id),
                        status=p.status,  # pyright: ignore[reportArgumentType]
                        completed=p.completed,
                    )
                    for p in people[coop.id]
                ],
                my_quest_id=me.day_quest_id if me and joined else None,
                conversation_id=chats.get(coop.id) if joined else None,
                expires_at=coop.expires_at,
                bonus_awarded=coop.bonus_awarded_at is not None
                if is_parts
                else quests.coop.bonus_awarded(people[coop.id]),
                kind=coop.kind,  # pyright: ignore[reportArgumentType]
                place=Place.model_validate(coop.place) if coop.place else None,
                starts_at=coop.starts_at,
                parts=[_part_schema(v, users, viewer_id) for v in parts[coop.id]]
                if is_parts
                else None,
            )
        )
    return out


async def coop_view(
    session: AsyncSession,
    user_id: uuid.UUID,
    coop_id: uuid.UUID,
    absent_status: CoopStatus = "invited",
    *,
    answered_offer: bool = False,
) -> Coop:
    """The co-op for a participant, or for a friend a part is offered to (or who has just
    answered the offer, and so no longer has it)."""
    coop = await quests.coop.get_coop(session, coop_id)
    me = await quests.coop.participant(session, coop_id, user_id) if coop else None
    if coop is None or (
        me is None
        and not answered_offer
        and not await quests.plans.has_pending_handoff(session, coop_id, user_id)
    ):
        raise day_problem(DayError("coop-not-found"))
    [view] = await build_coops(session, [(coop, me)], user_id, absent_status)
    return view


async def list_coops(session: AsyncSession, user: auth.User, now: datetime) -> list[Coop]:
    return await build_coops(session, await quests.coop.user_coops(session, user.id, now), user.id)


async def _check_friends(
    session: AsyncSession, user: auth.User, friend_ids: Sequence[uuid.UUID]
) -> None:
    if len(set(friend_ids)) != len(friend_ids) or user.id in friend_ids:
        raise Problem(422, "validation-failed", detail="Друзья повторяются")
    friends = await auth.get_users(session, list(friend_ids))
    for friend_id in friend_ids:
        friend = friends.get(friend_id)
        if (
            friend is None
            or friend.deletion_requested_at is not None
            or not await social.are_friends(session, user.id, friend_id)
        ):
            raise Problem(403, "not-friends", detail="Позвать можно только друзей")


def _slot(user: auth.User, now: datetime) -> quests.plans.Slot:
    day = day_clock.local_day(now, user.timezone)
    return day, day_clock.day_expires_at(day, user.timezone)


def completion_slots(session: AsyncSession, now: datetime) -> quests.plans.SlotsFor:
    """Each given user's day, for the quests of parts that open (the users' time zones live
    in `auth`, which `quests` does not import)."""

    async def slots_for(ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, quests.plans.Slot]:
        users = await auth.get_users(session, list(ids))
        return {uid: _slot(u, now) for uid, u in users.items() if u.deletion_requested_at is None}

    return slots_for


async def create_coop(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    quest_id: uuid.UUID,
    friend_ids: Sequence[uuid.UUID],
    now: datetime,
) -> Coop:
    await _check_friends(session, user, friend_ids)
    day = day_clock.local_day(now, user.timezone)
    try:
        coop = await quests.coop.create_coop(session, user.id, quest_id, friend_ids, day, now)
    except DayError as exc:
        raise day_problem(exc) from None
    await chat.create_group(session, coop.id, [user.id], now)
    await analytics.record(
        session,
        EventType.COOP_CREATED,
        user.id,
        {
            "coop_id": coop.id,
            "day_quest_id": quest_id,
            "category": coop.category,
            "invited": len(friend_ids),
            "kind": coop.kind,
            "parts": 0,
        },
        occurred_at=now,
    )
    for friend_id in friend_ids:
        await notify(
            session,
            friend_id,
            INVITE_KIND,
            {"coop_id": str(coop.id)},
            dedupe_key=f"{INVITE_KIND}:{coop.id}:{friend_id}",
        )
    await session.commit()
    await publish(session, realtime, COOP_UPDATED, {"coop_id": str(coop.id)})
    return await coop_view(session, user.id, coop.id)


async def accept_coop(
    session: AsyncSession, realtime: Realtime, user: auth.User, coop_id: uuid.UUID, now: datetime
) -> Coop:
    day = day_clock.local_day(now, user.timezone)
    try:
        coop, quest = await quests.coop.accept(
            session, coop_id, user.id, day, day_clock.day_expires_at(day, user.timezone), now
        )
    except DayError as exc:
        raise day_problem(exc) from None
    conversation = await chat.conversation_for_coop(session, coop.id)
    if conversation is not None:
        await chat.add_member(session, conversation.id, user.id, now)
    await analytics.record(
        session,
        EventType.COOP_ANSWERED,
        user.id,
        {"coop_id": coop.id, "answer": "accepted", "day_quest_id": quest.id if quest else None},
        occurred_at=now,
    )
    if quest is not None:
        await analytics.record(
            session,
            EventType.QUEST_TAKEN,
            user.id,
            {
                "day_quest_id": quest.id,
                "template_id": None,
                "source": quest.source,
                "category": quest.category,
                "position": quest.position,
            },
            occurred_at=now,
        )
    await session.commit()
    await publish(session, realtime, COOP_UPDATED, {"coop_id": str(coop.id)})
    return await coop_view(session, user.id, coop.id)


async def decline_coop(
    session: AsyncSession, realtime: Realtime, user: auth.User, coop_id: uuid.UUID, now: datetime
) -> Coop:
    try:
        coop, bonuses = await quests.coop.decline(
            session, coop_id, user.id, now, completion_slots(session, now)
        )
    except DayError as exc:
        raise day_problem(exc) from None
    await analytics.record(
        session,
        EventType.COOP_ANSWERED,
        user.id,
        {"coop_id": coop.id, "answer": "declined", "day_quest_id": None},
        occurred_at=now,
    )
    await record_bonuses(session, coop, bonuses, None, now)
    await session.commit()
    await publish(session, realtime, COOP_UPDATED, {"coop_id": str(coop.id)})
    return await coop_view(session, user.id, coop.id)


def _starts_in_day(starts_at: datetime | None, expires_at: datetime) -> None:
    if starts_at is not None and starts_at >= expires_at:
        raise Problem(422, "validation-failed", detail="Время должно быть до конца дня")


def _plan_spec(
    user: auth.User, body: CoopCreateInput, expires_at: datetime
) -> quests.plans.PlanSpec:
    allowed = {user.id, *body.friend_ids}
    _starts_in_day(body.starts_at, expires_at)
    parts: list[quests.plans.PartSpec] = []
    for i, part in enumerate(body.parts or []):
        if part.assignee_id not in allowed:
            raise Problem(422, "validation-failed", detail="Часть можно дать себе или другу")
        if part.opens_after is not None and part.opens_after >= i:
            raise Problem(422, "validation-failed", detail="Часть открывается после более ранней")
        _starts_in_day(part.starts_at, expires_at)
        parts.append(
            quests.plans.PartSpec(
                title=part.title,
                category=part.category or body.category,
                duration_min=part.duration_min or body.duration_min,
                assignee_id=part.assignee_id,
                place=part.place.model_dump(exclude_none=True) if part.place else None,
                starts_at=part.starts_at,
                opens_after=part.opens_after,
                items=part.items,
            )
        )
    if parts and all(p.opens_after is not None for p in parts):
        raise Problem(422, "validation-failed", detail="Нужна хотя бы одна часть без ожидания")
    return quests.plans.PlanSpec(
        title=body.title,
        category=body.category,
        duration_min=body.duration_min,
        description=body.description,
        outdoor=body.outdoor,
        place=body.place.model_dump(exclude_none=True) if body.place else None,
        starts_at=body.starts_at,
        parts=parts,
    )


async def create_plan(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    body: CoopCreateInput,
    now: datetime,
) -> Coop:
    """A co-op written directly (the assistant flows of M5): the same quest with a place and
    time, or parts with their own assignees."""
    await _check_friends(session, user, body.friend_ids)
    slot = _slot(user, now)
    spec = _plan_spec(user, body, slot[1])
    try:
        coop = await quests.plans.create_plan(session, user.id, spec, body.friend_ids, slot, now)
    except DayError as exc:
        raise day_problem(exc) from None
    await chat.create_group(session, coop.id, [user.id], now)
    parts = (await quests.plans.parts_of(session, [coop.id]))[coop.id]
    own = await quests.coop.participant(session, coop.id, user.id)
    await analytics.record(
        session,
        EventType.COOP_CREATED,
        user.id,
        {
            "coop_id": coop.id,
            "day_quest_id": own.day_quest_id if own else None,
            "category": coop.category,
            "invited": len(body.friend_ids),
            "kind": coop.kind,
            "parts": len(parts),
        },
        occurred_at=now,
    )
    for view in parts:
        if view.part.state == "open":
            await _part_opened(session, user.id, coop, view.part.id, now)
    for friend_id in body.friend_ids:
        await notify(
            session,
            friend_id,
            INVITE_KIND,
            {"coop_id": str(coop.id)},
            dedupe_key=f"{INVITE_KIND}:{coop.id}:{friend_id}",
        )
    await session.commit()
    await publish(session, realtime, COOP_UPDATED, {"coop_id": str(coop.id)})
    return await coop_view(session, user.id, coop.id)


async def _part_opened(
    session: AsyncSession, user_id: uuid.UUID, coop: quests.Coop, part_id: uuid.UUID, now: datetime
) -> None:
    await analytics.record(
        session,
        EventType.COOP_PART_OPENED,
        user_id,
        {"coop_id": coop.id, "part_id": part_id},
        occurred_at=now,
    )


async def record_progress(
    session: AsyncSession, user_id: uuid.UUID, progress: quests.plans.Progress, now: datetime
) -> int:
    """Events, notices and the bonus for the user who just completed a co-op quest; returns
    the bonus points this user got now."""
    coop = progress.coop
    if progress.completed_part_id is not None:
        await analytics.record(
            session,
            EventType.COOP_PART_COMPLETED,
            user_id,
            {"coop_id": coop.id, "part_id": progress.completed_part_id},
            occurred_at=now,
        )
    for part_id in progress.opened_part_ids:
        await _part_opened(session, user_id, coop, part_id, now)
    await record_bonuses(session, coop, progress.bonuses, user_id, now)
    if not progress.bonuses:
        return 0
    owners = await quests.plans.quest_owners(session, list(progress.bonuses))
    return sum(
        points for quest_id, points in progress.bonuses.items() if owners[quest_id] == user_id
    )


async def _joined_view(
    session: AsyncSession, coop_id: uuid.UUID, user_id: uuid.UUID
) -> quests.Coop:
    """Lock the co-op for a participant who has joined, else it is not theirs."""
    coop = await quests.coop.lock_coop(session, coop_id)
    me = await quests.coop.participant(session, coop_id, user_id) if coop else None
    if coop is None or me is None or me.status not in quests.coop.JOINED:
        raise day_problem(DayError("coop-not-found"))
    return coop


async def set_item(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    item_id: uuid.UUID,
    done: bool,
    now: datetime,
) -> Coop:
    coop = await quests.coop.get_coop(session, coop_id)
    me = await quests.coop.participant(session, coop_id, user.id) if coop else None
    if coop is None or me is None or me.status not in quests.coop.JOINED:
        raise day_problem(DayError("coop-not-found"))
    try:
        await quests.plans.tick_item(session, coop_id, part_id, item_id, user.id, done, now)
    except DayError as exc:
        raise day_problem(exc) from None
    await session.commit()
    await publish(session, realtime, COOP_UPDATED, {"coop_id": str(coop_id)})
    return await coop_view(session, user.id, coop_id)


async def offer_handoff(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    friend_id: uuid.UUID,
    now: datetime,
) -> Coop:
    if friend_id == user.id:
        raise day_problem(DayError("handoff-to-self"))
    friend = (await auth.get_users(session, [friend_id])).get(friend_id)
    if (
        friend is None
        or friend.deletion_requested_at is not None
        or not await social.are_friends(session, user.id, friend_id)
    ):
        raise Problem(403, "not-friends", detail="Передать часть можно только другу")
    coop = await _joined_view(session, coop_id, user.id)
    try:
        handoff = await quests.plans.offer_handoff(session, coop, part_id, user.id, friend_id, now)
    except DayError as exc:
        raise day_problem(exc) from None
    await analytics.record(
        session,
        EventType.COOP_PART_HANDED_OFF,
        user.id,
        {"coop_id": coop.id, "part_id": part_id, "to_user_id": friend_id},
        occurred_at=now,
    )
    await notify(
        session,
        friend_id,
        HANDOFF_KIND,
        {"coop_id": str(coop.id), "part_id": str(part_id)},
        dedupe_key=f"{HANDOFF_KIND}:{part_id}:{friend_id}:{int(handoff.created_at.timestamp())}",
    )
    await session.commit()
    await publish(
        session, realtime, COOP_UPDATED, {"coop_id": str(coop.id), "also": [str(friend_id)]}
    )
    return await coop_view(session, user.id, coop.id)


async def withdraw_handoff(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    now: datetime,
) -> Coop:
    coop = await _joined_view(session, coop_id, user.id)
    try:
        handoff = await quests.plans.withdraw_handoff(session, coop, part_id, user.id)
    except DayError as exc:
        raise day_problem(exc) from None
    await session.commit()
    await publish(
        session,
        realtime,
        COOP_UPDATED,
        {"coop_id": str(coop.id), "also": [str(handoff.to_user_id)]},
    )
    return await coop_view(session, user.id, coop.id)


async def accept_handoff(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    now: datetime,
) -> Coop:
    coop = await quests.plans.lock_for_handoff(session, coop_id, part_id)
    if coop is None:
        raise day_problem(DayError("part-not-found"))
    try:
        previous = await quests.plans.accept_handoff(
            session, coop, part_id, user.id, _slot(user, now), now
        )
    except DayError as exc:
        raise day_problem(exc) from None
    conversation = await chat.conversation_for_coop(session, coop.id)
    if conversation is not None:
        await chat.add_member(session, conversation.id, user.id, now)
    await analytics.record(
        session,
        EventType.COOP_HANDOFF_ANSWERED,
        user.id,
        {"coop_id": coop.id, "part_id": part_id, "answer": "accepted"},
        occurred_at=now,
    )
    await session.commit()
    await publish(
        session, realtime, COOP_UPDATED, {"coop_id": str(coop.id), "also": [str(previous)]}
    )
    return await coop_view(session, user.id, coop.id)


async def decline_handoff(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    now: datetime,
) -> Coop:
    coop = await quests.coop.lock_coop(session, coop_id)
    if coop is None:
        raise day_problem(DayError("part-not-found"))
    try:
        await quests.plans.decline_handoff(session, coop, part_id, user.id)
    except DayError as exc:
        raise day_problem(exc) from None
    await analytics.record(
        session,
        EventType.COOP_HANDOFF_ANSWERED,
        user.id,
        {"coop_id": coop.id, "part_id": part_id, "answer": "declined"},
        occurred_at=now,
    )
    await session.commit()
    await publish(session, realtime, COOP_UPDATED, {"coop_id": str(coop.id)})
    return await coop_view(session, user.id, coop.id, absent_status="declined", answered_offer=True)


async def record_bonuses(
    session: AsyncSession,
    coop: quests.Coop,
    bonuses: Mapping[uuid.UUID, int],
    completed_by: uuid.UUID | None,
    now: datetime,
) -> None:
    """Analytics for each bonus, and a bot notice to everyone but the one who just
    completed (they see it in the app)."""
    if not bonuses:
        return
    owners = await quests.plans.quest_owners(session, list(bonuses))
    for quest_id, points in bonuses.items():
        user_id = owners[quest_id]
        await analytics.record(
            session,
            EventType.COOP_BONUS,
            user_id,
            {"coop_id": coop.id, "day_quest_id": quest_id, "points": points},
            occurred_at=now,
        )
        if user_id != completed_by:
            await notify(
                session,
                user_id,
                BONUS_KIND,
                {"coop_id": str(coop.id), "points": points},
                dedupe_key=f"{BONUS_KIND}:{coop.id}:{user_id}",
            )


# --- realtime and bot notices -----------------------------------------------------------


async def _coop_updated(session: AsyncSession, params: Mapping[str, Any]) -> Delivery | None:
    coop_id = uuid.UUID(str(params["coop_id"]))
    people = (await quests.coop.participants(session, [coop_id]))[coop_id]
    if not people:
        return None
    # A friend a part is offered to follows the plan too; `also` names who was just removed.
    extra = [uuid.UUID(str(i)) for i in params.get("also", [])]
    extra += await quests.plans.handoff_recipients(session, coop_id)
    recipients = list(dict.fromkeys([p.user_id for p in people] + extra))
    return Delivery(recipients, {"type": "coop.updated", "coop_id": str(coop_id)})


BUILDERS[COOP_UPDATED] = _coop_updated


def invite_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> BotMessage | None:
        coop_id = uuid.UUID(str(params["coop_id"]))
        coop = await quests.coop.get_coop(session, coop_id)
        me = await quests.coop.participant(session, coop_id, user.id) if coop else None
        if coop is None or me is None or me.status != "invited":
            return None
        if datetime.now(UTC) >= coop.expires_at:
            return None
        owner = await auth.get_user(session, coop.owner_id)
        if owner is None or owner.deletion_requested_at is not None:
            return None
        if coop.kind == "parts":
            text = (
                f"{owner.first_name} зовёт тебя в совместный план «{coop.title}» 🤝\n"
                "У каждого своя часть, а если справятся все, каждому +50% очков."
            )
        else:
            text = (
                f"{owner.first_name} зовёт тебя на совместный квест «{coop.title}» 🤝\n"
                "Каждый делает его сам, а если справятся все, каждому +50% очков."
            )
        return BotMessage(
            text,
            app_button(settings, "Посмотреть", start_param=f"q{coop_id.hex}"),
        )

    return render


def bonus_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> BotMessage | None:
        coop_id = uuid.UUID(str(params["coop_id"]))
        coop = await quests.coop.get_coop(session, coop_id)
        if coop is None:
            return None
        return BotMessage(
            f"Все справились с совместным квестом «{coop.title}» 🎉 Бонус +{int(params['points'])}",
            app_button(settings, "Открыть", start_param=f"q{coop_id.hex}"),
        )

    return render


def handoff_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> BotMessage | None:
        coop_id = uuid.UUID(str(params["coop_id"]))
        part_id = uuid.UUID(str(params["part_id"]))
        handoff = await session.get(quests.CoopHandoff, part_id)
        part = await session.get(quests.CoopPart, part_id)
        coop = await quests.coop.get_coop(session, coop_id)
        if handoff is None or handoff.to_user_id != user.id or part is None or coop is None:
            return None
        if datetime.now(UTC) >= coop.expires_at:
            return None
        sender = await auth.get_user(session, handoff.from_user_id)
        if sender is None or sender.deletion_requested_at is not None:
            return None
        return BotMessage(
            f"{sender.first_name} просит тебя взять часть «{part.title}» в плане «{coop.title}» 🤝",
            app_button(settings, "Посмотреть", start_param=f"q{coop_id.hex}"),
        )

    return render


def register(settings: Settings) -> None:
    RENDERERS[INVITE_KIND] = invite_renderer(settings)
    RENDERERS[BONUS_KIND] = bonus_renderer(settings)
    RENDERERS[HANDOFF_KIND] = handoff_renderer(settings)
