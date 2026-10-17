"""Sign-in through the bot from native apps (ADR 0009).

The app creates a request and opens `t.me/<bot>?start=login_<code>`; the user confirms in
the bot (the confirmation comes from Telegram itself, so the Telegram user is trusted);
the app exchanges the request once with a secret only it knows. Only hashes of the code
and the secret are stored.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.auth.models import TelegramLoginRequest
from ayda.modules.auth.telegram import TelegramUser

REQUEST_TTL = timedelta(minutes=5)
MAX_REQUESTS_PER_CLIENT_HOUR = 20
CODE_PREFIX = "login_"
_KEEP = timedelta(days=1)


class LoginRequestError(Exception):
    """`code`: `too-many-requests`, `pending` or `invalid`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _hash(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def _client_key(secret: str, client: str) -> bytes:
    return hmac.new(secret.encode(), f"tg-login:{client}".encode(), hashlib.sha256).digest()


@dataclass(frozen=True)
class CreatedRequest:
    id: uuid.UUID
    code: str
    poll_secret: str
    expires_at: datetime


@dataclass(frozen=True)
class ApprovedRequest:
    telegram_user: TelegramUser
    link_user_id: uuid.UUID | None


async def create_request(
    session: AsyncSession,
    client: str,
    secret: str,
    link_user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> CreatedRequest:
    now = now or datetime.now(UTC)
    client_key = _client_key(secret, client)
    await session.execute(
        delete(TelegramLoginRequest).where(TelegramLoginRequest.created_at < now - _KEEP)
    )
    recent = await session.scalar(
        select(func.count()).where(
            TelegramLoginRequest.client_key == client_key,
            TelegramLoginRequest.created_at > now - timedelta(hours=1),
        )
    )
    if (recent or 0) >= MAX_REQUESTS_PER_CLIENT_HOUR:
        raise LoginRequestError("too-many-requests")
    # Telegram start parameters allow up to 64 characters of [A-Za-z0-9_-].
    code = secrets.token_urlsafe(16)
    poll_secret = secrets.token_urlsafe(32)
    request = TelegramLoginRequest(
        id=uuid7(),
        code_hash=_hash(code),
        secret_hash=_hash(poll_secret),
        client_key=client_key,
        link_user_id=link_user_id,
        expires_at=now + REQUEST_TTL,
        created_at=now,
    )
    session.add(request)
    return CreatedRequest(request.id, code, poll_secret, request.expires_at)


async def find_pending(
    session: AsyncSession, code: str, now: datetime | None = None
) -> TelegramLoginRequest | None:
    """The pending request behind a bot start parameter (without the `login_` prefix)."""
    now = now or datetime.now(UTC)
    return await session.scalar(
        select(TelegramLoginRequest).where(
            TelegramLoginRequest.code_hash == _hash(code),
            TelegramLoginRequest.status == "pending",
            TelegramLoginRequest.expires_at > now,
        )
    )


async def approve_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    tg: TelegramUser,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    request = await session.scalar(
        select(TelegramLoginRequest).where(TelegramLoginRequest.id == request_id).with_for_update()
    )
    if request is None or request.status != "pending" or request.expires_at <= now:
        return False
    request.status = "approved"
    request.approved_at = now
    request.telegram_id = tg.id
    request.first_name = tg.first_name
    request.last_name = tg.last_name
    request.username = tg.username
    return True


async def exchange_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    poll_secret: str,
    now: datetime | None = None,
) -> ApprovedRequest:
    """Marks an approved request used and returns who confirmed it.

    Raises LoginRequestError("pending") until confirmed and ("invalid") for a wrong secret,
    an expired, unknown or already used request.
    """
    now = now or datetime.now(UTC)
    request = await session.scalar(
        select(TelegramLoginRequest).where(TelegramLoginRequest.id == request_id).with_for_update()
    )
    if request is None or not hmac.compare_digest(request.secret_hash, _hash(poll_secret)):
        raise LoginRequestError("invalid")
    if request.status == "pending":
        if request.expires_at <= now:
            raise LoginRequestError("invalid")
        raise LoginRequestError("pending")
    if request.status != "approved" or request.telegram_id is None:
        raise LoginRequestError("invalid")
    # A confirmed request must be picked up soon after it was confirmed.
    if request.approved_at is None or now - request.approved_at > REQUEST_TTL:
        raise LoginRequestError("invalid")
    request.status = "used"
    return ApprovedRequest(
        TelegramUser(
            id=request.telegram_id,
            first_name=request.first_name or "",
            last_name=request.last_name,
            username=request.username,
            photo_url=None,
        ),
        request.link_user_id,
    )
