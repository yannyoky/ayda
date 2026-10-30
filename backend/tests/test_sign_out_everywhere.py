"""Audit V5: a phished Telegram confirmation is reported by the bot and can be undone."""

import httpx
from sqlalchemy import select

from ayda.app import notifications, security
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from tests.contract import assert_matches
from tests.helpers import sign_in
from tests.test_bot import FakeSender
from tests.test_telegram_login import confirm, exchange, start


async def native_session(client: httpx.AsyncClient, database: Database) -> dict[str, str]:
    request = await start(client)
    await confirm(database, request)
    ok = await exchange(client, request)
    assert ok.status_code == 200, ok.text
    return ok.json()


async def test_the_bot_reports_a_native_sign_in_even_with_push_on(
    client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    await sign_in(client, telegram_id=777, name="Петя")  # the Mini App account
    native = await native_session(client, database)
    headers = {"Authorization": f"Bearer {native['access_token']}"}
    # The new device registers for push: the notice must still go to Telegram.
    device = await client.put(
        "/me/devices", json={"platform": "android", "token": "fcm-token"}, headers=headers
    )
    assert device.status_code in (200, 201), device.text

    security.register(settings)
    sender = FakeSender()
    async with database.sessionmaker() as session:
        [job] = list(await session.scalars(select(Job).where(Job.kind == "notify.send")))
        assert job.payload["kind"] == security.NEW_SIGN_IN_KIND
        result = await notifications.send(session, sender, job.payload)
        await session.commit()
    assert result.sent
    [(chat_id, message)] = sender.sent
    assert chat_id == 777 and "другого устройства" in message.text
    assert message.button is not None and message.button.url.endswith("startapp=signout")


async def test_a_first_sign_in_is_not_reported(
    client: httpx.AsyncClient, database: Database
) -> None:
    await native_session(client, database)
    async with database.sessionmaker() as session:
        assert list(await session.scalars(select(Job).where(Job.kind == "notify.send"))) == []


async def test_sign_out_everywhere_ends_every_session(
    client: httpx.AsyncClient, database: Database
) -> None:
    mini_app = await sign_in(client, telegram_id=777, name="Петя")
    native = await native_session(client, database)
    native_headers = {"Authorization": f"Bearer {native['access_token']}"}
    assert (await client.get("/me", headers=native_headers)).status_code == 200

    done = await client.post("/auth/sign-out-everywhere", headers=mini_app.headers)
    assert done.status_code == 204
    assert_matches(done, "signOutEverywhere")

    assert (await client.get("/me", headers=native_headers)).status_code == 401
    assert (await client.get("/me", headers=mini_app.headers)).status_code == 401
    refreshed = await client.post("/auth/refresh", json={"refresh_token": native["refresh_token"]})
    assert refreshed.status_code == 401
    # Signing in again works.
    again = await sign_in(client, telegram_id=777, name="Петя")
    assert (await client.get("/me", headers=again.headers)).status_code == 200
    assert (await client.post("/auth/sign-out-everywhere")).status_code == 401
