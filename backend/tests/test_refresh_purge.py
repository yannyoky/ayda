"""Audit M8: expired refresh tokens are deleted, live ones stay."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx

from ayda.core.db import Database
from ayda.modules import auth
from tests.helpers import sign_in


async def test_expired_refresh_tokens_are_purged(
    client: httpx.AsyncClient, database: Database
) -> None:
    user = await sign_in(client, telegram_id=777, name="Петя")
    async with database.sessionmaker() as session:
        await auth.issue_refresh_token(session, uuid.UUID(user.user_id))
        await auth.issue_refresh_token(session, uuid.UUID(user.user_id))
        await session.commit()
        later = datetime.now(UTC) + timedelta(days=61)
        assert await auth.purge_expired_refresh_tokens(session, datetime.now(UTC)) == 0
        assert await auth.purge_expired_refresh_tokens(session, later) >= 2
        await session.commit()
