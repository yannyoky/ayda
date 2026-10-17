"""Sign-in by a one-time email code (ADR 0009).

Codes and rate-limit rows are keyed by an HMAC of the address, so an address is stored
only once its owner signs in (as an `email` identity). Neither the address nor the code
is ever logged.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.auth.models import EmailCode, EmailSend

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(minutes=1)
MAX_SENDS_PER_EMAIL_HOUR = 5
MAX_SENDS_PER_CLIENT_HOUR = 20
_KEEP_SENDS = timedelta(days=1)

# Deliberately simple: one @, no spaces, a dot in the domain. The code proves the rest.
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")


class EmailError(Exception):
    """`code` is a short machine-readable reason; never contains the address or the code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise EmailError("invalid-email")
    return email


def _key(secret: str, kind: str, value: str) -> bytes:
    return hmac.new(secret.encode(), f"{kind}:{value}".encode(), hashlib.sha256).digest()


def _code_hash(secret: str, email_key: bytes, code: str) -> bytes:
    return hmac.new(secret.encode(), email_key + code.encode(), hashlib.sha256).digest()


@dataclass(frozen=True)
class IssuedCode:
    code: str
    expires_at: datetime


async def issue_code(
    session: AsyncSession,
    email: str,
    client: str,
    secret: str,
    now: datetime | None = None,
) -> IssuedCode:
    """Create a new code for a normalized email, replacing the previous one.

    Raises EmailError("too-many-codes") when the email or the client hit a limit.
    """
    now = now or datetime.now(UTC)
    email_key = _key(secret, "email", email)
    client_key = _key(secret, "client", client)
    await session.execute(delete(EmailSend).where(EmailSend.sent_at < now - _KEEP_SENDS))

    hour_ago = now - timedelta(hours=1)
    by_email = await session.execute(
        select(func.count(), func.max(EmailSend.sent_at)).where(
            EmailSend.email_key == email_key, EmailSend.sent_at > hour_ago
        )
    )
    email_count, newest = by_email.one()
    last_sent = cast("datetime | None", newest)
    if email_count >= MAX_SENDS_PER_EMAIL_HOUR or (
        last_sent is not None and now - last_sent < RESEND_AFTER
    ):
        raise EmailError("too-many-codes")
    client_count = await session.scalar(
        select(func.count()).where(EmailSend.client_key == client_key, EmailSend.sent_at > hour_ago)
    )
    if (client_count or 0) >= MAX_SENDS_PER_CLIENT_HOUR:
        raise EmailError("too-many-codes")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + CODE_TTL
    values = {
        "code_hash": _code_hash(secret, email_key, code),
        "attempts": 0,
        "expires_at": expires_at,
        "created_at": now,
    }
    await session.execute(
        insert(EmailCode)
        .values(email_key=email_key, **values)
        .on_conflict_do_update(index_elements=[EmailCode.email_key], set_=values)
    )
    session.add(EmailSend(email_key=email_key, client_key=client_key, sent_at=now))
    return IssuedCode(code=code, expires_at=expires_at)


async def check_code(
    session: AsyncSession, email: str, code: str, secret: str, now: datetime | None = None
) -> None:
    """Consume the code on success; count a wrong attempt otherwise.

    Raises EmailError("invalid-code") for a wrong, used, expired or exhausted code. The
    caller must commit even on failure so that wrong attempts are counted.
    """
    now = now or datetime.now(UTC)
    email_key = _key(secret, "email", email)
    row = await session.scalar(
        select(EmailCode).where(EmailCode.email_key == email_key).with_for_update()
    )
    if row is None or row.expires_at <= now or row.attempts >= MAX_ATTEMPTS:
        raise EmailError("invalid-code")
    if not hmac.compare_digest(row.code_hash, _code_hash(secret, email_key, code)):
        row.attempts += 1
        raise EmailError("invalid-code")
    await session.delete(row)
