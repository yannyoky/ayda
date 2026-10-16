import io
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text, update

from ayda.app import privacy
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.core.logging import RedactingFilter, redact
from ayda.modules import auth, quests, social
from ayda.worker import build_worker
from tests.helpers import make_init_data, sign_in
from tests.test_bot import FakeSender
from tests.test_day import forecast, use_tools
from tests.test_feed import befriend, post

SECRET = "Сдать анализы в поликлинике"


@pytest.mark.parametrize(
    ("raw", "leak"),
    [
        (make_init_data(), "auth_date=1"),
        ('{"init_data": "query_id=AAH1&user=%7B%22id%22"}', "AAH1"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "eyJ"),
        ("token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1 failed", "AAHdq"),
        ("GET /api/v1/cities?lat=54.7104&lon=20.4522 200", "54.71"),
        ('{"latitude": 54.7104, "longitude": 20.4522}', "20.45"),
        (f'{{"text": "{SECRET}", "mood": "tired"}}', "поликлиник"),
        ('{"caption": "мой адрес", "title": "x"}', "адрес"),
        ("https://s3/x?X-Amz-Signature=abcdef123&X-Amz-Credential=key", "abcdef123"),
    ],
)
def test_redaction(raw: str, leak: str) -> None:
    cleaned = redact(raw)
    assert leak not in cleaned
    assert "[redacted]" in cleaned


def test_filter_applies_to_formatted_args() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    logger = logging.getLogger("test.privacy")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning("sign-in with %s for %s", make_init_data(), "Bearer abc.def.ghi")
        logger.warning("body %s", {"text": SECRET})
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert "hash=[redacted]" in output
    assert "abc.def" not in output
    assert SECRET not in output


async def count(database: Database, sql: str, **params: object) -> int:
    async with database.sessionmaker() as session:
        return int((await session.execute(text(sql), params)).scalar_one())


async def test_account_deletion_erases_and_anonymizes(
    app: FastAPI, client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    use_tools(app, [], forecast())
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    await befriend(client, alice, bob)
    await client.put("/me/goals", json={"goal_codes": ["learn"]}, headers=alice.headers)
    await client.post(
        "/me/habits", json={"direction": "less", "text": "дота"}, headers=alice.headers
    )
    await client.put(
        "/days/today/checkin", json={"text": SECRET, "mood": "normal"}, headers=alice.headers
    )
    alice_post = await post(client, database, alice, "friends")
    bob_post = await post(client, database, bob, "routine")
    await client.put(f"/posts/{alice_post}/like", headers=bob.headers)
    await client.post(f"/posts/{alice_post}/comments", json={"text": "ок"}, headers=bob.headers)
    await client.put(f"/posts/{bob_post}/like", headers=alice.headers)
    await client.post(f"/posts/{bob_post}/comments", json={"text": "ура"}, headers=alice.headers)
    await client.post("/invites", headers=alice.headers)

    response = await client.delete("/me", headers=alice.headers)

    assert response.status_code == 202
    assert (await client.get("/me", headers=alice.headers)).status_code == 401
    assert (await client.delete("/me", headers=alice.headers)).status_code == 401

    worker = build_worker(settings, database, sender=FakeSender())
    while await worker.run_one():
        pass

    alice_id = uuid.UUID(alice.user_id)
    for table, column in [
        ("auth.users", "id"),
        ("auth.consents", "user_id"),
        ("habits.user_goals", "user_id"),
        ("habits.user_habits", "user_id"),
        ("quests.checkins", "user_id"),
        ("quests.day_pools", "user_id"),
        ("quests.day_quests", "user_id"),
        ("quests.points_ledger", "user_id"),
        ("quests.streaks", "user_id"),
        ("social.posts", "author_id"),
        ("social.comments", "author_id"),
        ("social.likes", "user_id"),
        ("social.media", "owner_id"),
        ("social.invites", "inviter_id"),
        ("analytics.events", "user_id"),
    ]:
        left = await count(
            database, f"SELECT count(*) FROM {table} WHERE {column} = :u", u=alice_id
        )
        assert left == 0, table
    assert await count(database, "SELECT count(*) FROM social.friendships") == 0
    assert (
        await count(
            database,
            "SELECT count(*) FROM analytics.events WHERE payload::text LIKE :u",
            u=f"%{alice.user_id}%",
        )
        == 0
    )
    # Anonymized, not deleted.
    assert (
        await count(
            database, "SELECT count(*) FROM analytics.events WHERE type = 'checkin_submitted'"
        )
        == 1
    )
    # Bob's own data stays; Alice's comment and like on it are gone.
    async with database.sessionmaker() as session:
        bob_left = await session.get(social.Post, uuid.UUID(bob_post))
        bob_comments = await session.scalar(select(func.count()).select_from(social.Comment))
        files = list(await session.scalars(select(Job).where(Job.kind == "media.delete_files")))
    assert bob_left is not None and bob_comments == 0
    # No S3 here: the file deletion is queued and retried by the worker.
    assert files and any(k.startswith("photos/") for k in files[0].payload["keys"])

    again = await client.post("/auth/telegram", json={"init_data": make_init_data(1001, "Алиса")})
    assert again.status_code == 200 and again.json()["user"]["id"] != alice.user_id


async def test_old_checkin_texts_are_purged(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    use_tools(app, [], forecast())
    user = await sign_in(client)
    await client.put(
        "/days/today/checkin", json={"text": SECRET, "mood": "normal"}, headers=user.headers
    )
    now = datetime.now(UTC)
    async with database.sessionmaker() as session:
        assert await privacy.purge_old_checkin_texts(session, now) == 0
        await session.execute(update(quests.Checkin).values(updated_at=now - timedelta(days=31)))
        assert await privacy.purge_old_checkin_texts(session, now) == 1
        await session.commit()
        checkin = (await session.scalars(select(quests.Checkin))).one()
    assert checkin.text is None and checkin.parsed


async def test_erase_ignores_users_who_did_not_ask(
    client: httpx.AsyncClient, database: Database
) -> None:
    user = await sign_in(client)
    async with database.sessionmaker() as session:
        assert not await privacy.erase_account(session, uuid.UUID(user.user_id))
        assert await auth.get_user(session, uuid.UUID(user.user_id)) is not None
