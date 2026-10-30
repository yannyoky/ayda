"""Ending every session of a user at once ("sign out everywhere", audit V5)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.auth.devices import forget_user_devices
from ayda.modules.auth.models import User
from ayda.modules.auth.refresh import revoke_user_refresh_tokens


async def end_all_sessions(session: AsyncSession, user: User, now: datetime | None = None) -> None:
    """Refuse access tokens issued so far, revoke every refresh token and forget push devices."""
    now = now or datetime.now(UTC)
    user.sessions_revoked_at = now
    await revoke_user_refresh_tokens(session, user.id, now)
    await forget_user_devices(session, user.id)


def token_revoked(user: User, issued_at: datetime) -> bool:
    return user.sessions_revoked_at is not None and issued_at < user.sessions_revoked_at
