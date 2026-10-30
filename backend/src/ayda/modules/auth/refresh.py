"""Rotating refresh tokens for native apps (ADR 0009).

A token is a random string shown to the client once; only its SHA-256 is stored. Each
use returns a new token of the same family; presenting a used token again revokes the
whole family, so a stolen token stops working for both the thief and the owner.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.auth.models import RefreshToken

REFRESH_TTL = timedelta(days=60)


class RefreshError(Exception):
    pass


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


async def issue_refresh_token(
    session: AsyncSession,
    user_id: uuid.UUID,
    family_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    now = now or datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    expires_at = now + REFRESH_TTL
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or uuid7(),
            token_hash=_hash(token),
            expires_at=expires_at,
            created_at=now,
        )
    )
    return token, expires_at


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def rotate_refresh_token(
    session: AsyncSession, token: str, now: datetime | None = None
) -> tuple[uuid.UUID, str, datetime]:
    """Returns the user id and a new token. On reuse, revokes the family and raises; the
    caller must commit even then so the revocation sticks."""
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(token)).with_for_update()
    )
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise RefreshError("invalid")
    if row.used_at is not None:
        await _revoke_family(session, row.family_id, now)
        raise RefreshError("reused")
    row.used_at = now
    new_token, expires_at = await issue_refresh_token(session, row.user_id, row.family_id, now)
    return row.user_id, new_token, expires_at


async def revoke_refresh_token(
    session: AsyncSession, token: str, now: datetime | None = None
) -> None:
    now = now or datetime.now(UTC)
    family_id = await session.scalar(
        select(RefreshToken.family_id).where(RefreshToken.token_hash == _hash(token))
    )
    if family_id is not None:
        await _revoke_family(session, family_id, now)


async def revoke_user_refresh_tokens(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now or datetime.now(UTC))
    )


async def purge_expired_refresh_tokens(session: AsyncSession, now: datetime) -> int:
    """Delete refresh tokens past their expiry (audit M8). Used ones are kept until then:
    presenting a used token is how a stolen one is detected."""
    result = await session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
    return result.rowcount or 0  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
