"""Co-op quests at a distance (US-18) across modules: the quest and its bonus (quests),
friendships (social), names (auth), the shared chat (chat), realtime and bot notices."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import Coop, CoopParticipant
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


async def build_coops(
    session: AsyncSession,
    rows: Sequence[tuple[quests.Coop, quests.CoopParticipant]],
) -> list[Coop]:
    """Co-ops as one viewer sees them; `rows` pair each co-op with the viewer's place."""
    ids = [c.id for c, _ in rows]
    people = await quests.coop.participants(session, ids)
    chats = await chat.conversations_for_coops(session, ids)
    users = await auth.get_users(session, list({p.user_id for ps in people.values() for p in ps}))
    out: list[Coop] = []
    for coop, me in rows:
        joined = me.status in quests.coop.JOINED
        out.append(
            Coop(
                id=coop.id,
                title=coop.title,
                category=coop.category,  # pyright: ignore[reportArgumentType]
                duration_min=coop.duration_min,
                owner=user_summary(users.get(coop.owner_id), coop.owner_id),
                my_status=me.status,  # pyright: ignore[reportArgumentType]
                participants=[
                    CoopParticipant(
                        user=user_summary(users.get(p.user_id), p.user_id),
                        status=p.status,  # pyright: ignore[reportArgumentType]
                        completed=p.completed,
                    )
                    for p in people[coop.id]
                ],
                my_quest_id=me.day_quest_id if joined else None,
                conversation_id=chats.get(coop.id) if joined else None,
                expires_at=coop.expires_at,
                bonus_awarded=quests.coop.bonus_awarded(people[coop.id]),
            )
        )
    return out


async def coop_view(session: AsyncSession, user_id: uuid.UUID, coop_id: uuid.UUID) -> Coop:
    coop = await quests.coop.get_coop(session, coop_id)
    me = await quests.coop.participant(session, coop_id, user_id) if coop else None
    if coop is None or me is None:
        raise day_problem(DayError("coop-not-found"))
    [view] = await build_coops(session, [(coop, me)])
    return view


async def list_coops(session: AsyncSession, user: auth.User, now: datetime) -> list[Coop]:
    return await build_coops(session, await quests.coop.user_coops(session, user.id, now))


async def create_coop(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    quest_id: uuid.UUID,
    friend_ids: Sequence[uuid.UUID],
    now: datetime,
) -> Coop:
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
        {"coop_id": coop.id, "answer": "accepted", "day_quest_id": quest.id},
        occurred_at=now,
    )
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
        coop, bonuses = await quests.coop.decline(session, coop_id, user.id, now)
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
    owners = {
        p.day_quest_id: p.user_id
        for p in (await quests.coop.participants(session, [coop.id]))[coop.id]
        if p.day_quest_id
    }
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
    return Delivery([p.user_id for p in people], {"type": "coop.updated", "coop_id": str(coop_id)})


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
        return BotMessage(
            f"{owner.first_name} зовёт тебя на совместный квест «{coop.title}» 🤝\n"
            "Каждый делает его сам, а если справятся все, каждому +50% очков.",
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


def register(settings: Settings) -> None:
    RENDERERS[INVITE_KIND] = invite_renderer(settings)
    RENDERERS[BONUS_KIND] = bonus_renderer(settings)
