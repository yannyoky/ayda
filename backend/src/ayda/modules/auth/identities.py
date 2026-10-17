"""Sign-in methods of a user: list, link and unlink (ADR 0009).

`auth.users.telegram_id` mirrors the `telegram` identity, because the bot and the Mini App
find users by it.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.auth.models import User, UserIdentity
from ayda.modules.auth.telegram import TelegramUser


class IdentityError(Exception):
    """`code`: `taken` (belongs to another user), `not-found` or `last-identity`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def list_identities(session: AsyncSession, user_id: uuid.UUID) -> list[UserIdentity]:
    rows = await session.scalars(
        select(UserIdentity)
        .where(UserIdentity.user_id == user_id)
        .order_by(UserIdentity.created_at, UserIdentity.id)
    )
    return list(rows)


async def _link(
    session: AsyncSession, user_id: uuid.UUID, provider: str, subject: str
) -> UserIdentity:
    existing = await session.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider, UserIdentity.subject == subject
        )
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise IdentityError("taken")
        return existing
    identity = UserIdentity(id=uuid7(), user_id=user_id, provider=provider, subject=subject)
    session.add(identity)
    await session.flush()
    return identity


async def link_email(session: AsyncSession, user: User, email: str) -> UserIdentity:
    """Attach a normalized, verified email to the user."""
    return await _link(session, user.id, "email", email)


async def link_telegram(session: AsyncSession, user: User, tg: TelegramUser) -> UserIdentity:
    """Attach a Telegram account confirmed in the bot. A user has at most one."""
    if user.telegram_id is not None and user.telegram_id != tg.id:
        raise IdentityError("taken")
    owner = await session.scalar(select(User.id).where(User.telegram_id == tg.id))
    if owner is not None and owner != user.id:
        raise IdentityError("taken")
    identity = await _link(session, user.id, "telegram", str(tg.id))
    user.telegram_id = tg.id
    user.username = tg.username
    if not user.first_name.strip():
        user.first_name = tg.first_name
        user.last_name = tg.last_name
    return identity


async def unlink_identity(session: AsyncSession, user: User, identity_id: uuid.UUID) -> None:
    identity = await session.get(UserIdentity, identity_id)
    if identity is None or identity.user_id != user.id:
        raise IdentityError("not-found")
    count = await session.scalar(select(func.count()).where(UserIdentity.user_id == user.id))
    if (count or 0) <= 1:
        raise IdentityError("last-identity")
    if identity.provider == "telegram":
        user.telegram_id = None
        user.username = None
    await session.delete(identity)
