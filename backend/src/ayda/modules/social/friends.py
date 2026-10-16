"""Invites by Telegram link and mutual friendships."""

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.social.models import Friendship, Invite

INVITE_TTL = timedelta(days=7)
# A fresh link is reused while it has most of its life left, so repeated taps on
# "invite" don't pile up codes.
REUSE_IF_LEFT = timedelta(days=6)
MAX_INVITES_PER_DAY = 20


class InviteError(Exception):
    """`code`: invite-not-found, invite-expired or own-invite."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class InviteLimitError(Exception):
    pass


def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if a < b else (b, a)


async def create_invite(session: AsyncSession, inviter_id: uuid.UUID, now: datetime) -> Invite:
    fresh = await session.scalar(
        select(Invite)
        .where(Invite.inviter_id == inviter_id, Invite.expires_at > now + REUSE_IF_LEFT)
        .order_by(Invite.created_at.desc())
        .limit(1)
    )
    if fresh is not None:
        return fresh
    today = await session.scalar(
        select(func.count())
        .select_from(Invite)
        .where(Invite.inviter_id == inviter_id, Invite.created_at > now - timedelta(days=1))
    )
    if (today or 0) >= MAX_INVITES_PER_DAY:
        raise InviteLimitError
    invite = Invite(
        code=secrets.token_urlsafe(9),  # 12 URL-safe characters
        inviter_id=inviter_id,
        created_at=now,
        expires_at=now + INVITE_TTL,
    )
    session.add(invite)
    await session.flush()
    return invite


async def accept_invite(
    session: AsyncSession, code: str, user_id: uuid.UUID, now: datetime
) -> tuple[uuid.UUID, datetime]:
    """Create the friendship (idempotent); returns (inviter id, friends since)."""
    invite = await session.get(Invite, code)
    if invite is None:
        raise InviteError("invite-not-found")
    if invite.inviter_id == user_id:
        raise InviteError("own-invite")
    low, high = _pair(invite.inviter_id, user_id)
    existing = await session.get(Friendship, (low, high))
    if existing is not None:
        return invite.inviter_id, existing.created_at
    if invite.expires_at <= now:
        raise InviteError("invite-expired")
    await session.execute(
        insert(Friendship)
        .values(user_low=low, user_high=high, created_at=now)
        .on_conflict_do_nothing()
    )
    friendship = await session.get(Friendship, (low, high), populate_existing=True)
    assert friendship is not None
    return invite.inviter_id, friendship.created_at


async def friends(session: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    """Friend id -> friends since."""
    rows = await session.execute(
        select(Friendship.user_low, Friendship.user_high, Friendship.created_at).where(
            or_(Friendship.user_low == user_id, Friendship.user_high == user_id)
        )
    )
    return {(high if low == user_id else low): since for low, high, since in rows}


async def are_friends(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    return await session.get(Friendship, _pair(a, b)) is not None


async def remove_friend(session: AsyncSession, user_id: uuid.UUID, friend_id: uuid.UUID) -> bool:
    low, high = _pair(user_id, friend_id)
    result = await session.execute(
        delete(Friendship)
        .where(Friendship.user_low == low, Friendship.user_high == high)
        .returning(Friendship.user_low)
    )
    return result.first() is not None
