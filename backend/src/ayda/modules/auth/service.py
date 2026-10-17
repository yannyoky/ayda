import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.auth.models import Consent, User, UserIdentity
from ayda.modules.auth.refresh import revoke_user_refresh_tokens
from ayda.modules.auth.telegram import TelegramUser

# Version of the personal data processing consent the user must accept (docs/privacy).
CURRENT_CONSENT_VERSION = "2026-10-16"


async def upsert_telegram_user(session: AsyncSession, tg: TelegramUser) -> tuple[User, bool]:
    """Find the user by Telegram id or create one, refreshing name and avatar.

    Returns the user and whether it was created now.
    """
    values: dict[str, str | None] = {
        "first_name": tg.first_name,
        "last_name": tg.last_name,
        "username": tg.username,
    }
    # Sign-in through the bot carries no photo; keep the one from the Mini App then.
    if tg.photo_url is not None:
        values["avatar_url"] = tg.photo_url
    new_id = uuid7()
    stmt = (
        insert(User)
        .values(id=new_id, telegram_id=tg.id, **values)
        .on_conflict_do_update(index_elements=[User.telegram_id], set_=values)
        .returning(User)
    )
    user = (await session.execute(stmt)).scalar_one()
    await session.refresh(user)
    await _add_identity(session, user.id, "telegram", str(tg.id))
    return user, user.id == new_id


async def _add_identity(
    session: AsyncSession, user_id: uuid.UUID, provider: str, subject: str
) -> None:
    await session.execute(
        insert(UserIdentity)
        .values(id=uuid7(), user_id=user_id, provider=provider, subject=subject)
        .on_conflict_do_nothing(index_elements=[UserIdentity.provider, UserIdentity.subject])
    )


async def find_or_create_email_user(session: AsyncSession, email: str) -> tuple[User, bool]:
    """The user signed in with this normalized email, or a new one with an empty name.

    Returns the user and whether it was created now.
    """
    user_id = await session.scalar(
        select(UserIdentity.user_id).where(
            UserIdentity.provider == "email", UserIdentity.subject == email
        )
    )
    if user_id is not None:
        user = await session.get(User, user_id)
        assert user is not None  # identities cascade with their user
        return user, False
    user = User(id=uuid7(), telegram_id=None, first_name="")
    session.add(user)
    await session.flush()
    await _add_identity(session, user.id, "email", email)
    # A concurrent sign-in with the same email may have won; use its user.
    owner = await session.scalar(
        select(UserIdentity.user_id).where(
            UserIdentity.provider == "email", UserIdentity.subject == email
        )
    )
    if owner != user.id:
        await session.delete(user)
        winner = await session.get(User, owner)
        assert winner is not None
        return winner, False
    await session.refresh(user)
    return user, True


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_users(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    rows = await session.execute(select(User).where(User.id.in_(user_ids)))
    return {u.id: u for u in rows.scalars()}


async def user_city_ids(session: AsyncSession) -> list[int]:
    """Distinct cities of active users (for loading local events)."""
    rows = await session.scalars(
        select(User.city_id)
        .where(User.city_id.is_not(None), User.deletion_requested_at.is_(None))
        .distinct()
    )
    return sorted(i for i in rows if i is not None)


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


async def request_deletion(session: AsyncSession, user: User) -> None:
    """Sign-out everywhere is immediate: tokens of a user with this mark are rejected."""
    if user.deletion_requested_at is None:
        user.deletion_requested_at = datetime.now(UTC)
    await revoke_user_refresh_tokens(session, user.id)


async def delete_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """The last step of erasure; consents go with the user (ON DELETE CASCADE)."""
    await session.execute(delete(User).where(User.id == user_id))
