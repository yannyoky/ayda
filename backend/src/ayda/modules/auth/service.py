import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.auth.models import Consent, User
from ayda.modules.auth.telegram import TelegramUser

# Version of the personal data processing consent the user must accept (docs/privacy).
CURRENT_CONSENT_VERSION = "2026-10-16"


async def upsert_telegram_user(session: AsyncSession, tg: TelegramUser) -> tuple[User, bool]:
    """Find the user by Telegram id or create one, refreshing name and avatar.

    Returns the user and whether it was created now.
    """
    values = {
        "first_name": tg.first_name,
        "last_name": tg.last_name,
        "username": tg.username,
        "avatar_url": tg.photo_url,
    }
    new_id = uuid7()
    stmt = (
        insert(User)
        .values(id=new_id, telegram_id=tg.id, **values)
        .on_conflict_do_update(index_elements=[User.telegram_id], set_=values)
        .returning(User)
    )
    user = (await session.execute(stmt)).scalar_one()
    await session.refresh(user)
    return user, user.id == new_id


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_users(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    rows = await session.execute(select(User).where(User.id.in_(user_ids)))
    return {u.id: u for u in rows.scalars()}


async def accepted_consent_versions(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await session.execute(select(Consent.version).where(Consent.user_id == user_id))
    return set(rows.scalars())


async def consent_required(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    accepted = await accepted_consent_versions(session, user_id)
    return None if CURRENT_CONSENT_VERSION in accepted else CURRENT_CONSENT_VERSION


async def accept_consent(session: AsyncSession, user_id: uuid.UUID, version: str) -> None:
    if version in await accepted_consent_versions(session, user_id):
        return
    session.add(Consent(user_id=user_id, version=version, accepted_at=datetime.now(UTC)))


async def mark_bot_reachable(session: AsyncSession, telegram_id: int, reachable: bool) -> None:
    """The bot can't message a user who blocked it; /start makes them reachable again."""
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(bot_reachable=reachable)
    )
