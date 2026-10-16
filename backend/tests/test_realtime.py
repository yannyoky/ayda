import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from ayda.app import realtime as app_realtime
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.core.realtime import Realtime, RealtimeUnavailable, personal_channel
from ayda.main import create_app
from ayda.worker import build_worker
from tests.contract import assert_matches
from tests.helpers import sign_in
from tests.realtime_helpers import (
    CENTRIFUGO_API_KEY,
    CENTRIFUGO_TOKEN_SECRET,
    CENTRIFUGO_URL,
    centrifugo_client,
    require_centrifugo,
)

TEST_KIND = "test.ping"


async def _build_ping(_: Any, params: Mapping[str, Any]) -> app_realtime.Delivery | None:
    users = [uuid.UUID(u) for u in params["users"]]
    return app_realtime.Delivery(users, {"type": "test.ping", "n": params["n"]})


app_realtime.BUILDERS[TEST_KIND] = _build_ping


def _with_centrifugo(settings: Settings, api_url: str | None = None) -> Settings:
    return settings.model_copy(
        update={
            "centrifugo_api_url": api_url or f"{CENTRIFUGO_URL}/api",
            "centrifugo_public_url": CENTRIFUGO_URL.replace("http", "ws", 1)
            + "/connection/websocket",
            "centrifugo_api_key": SecretStr(CENTRIFUGO_API_KEY),
            "centrifugo_token_secret": SecretStr(CENTRIFUGO_TOKEN_SECRET),
        }
    )


@pytest.fixture
def rt_settings(settings: Settings) -> Settings:
    return _with_centrifugo(settings)


@pytest.fixture
async def rt_client(rt_settings: Settings) -> Any:
    app: FastAPI = create_app(rt_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    await app.state.db.dispose()


async def test_token_needs_sign_in(client: httpx.AsyncClient) -> None:
    response = await client.post("/realtime/token")
    assert response.status_code == 401
    assert_matches(response, "getRealtimeToken")


async def test_token_unavailable_without_secret(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    response = await client.post("/realtime/token", headers=me.headers)
    assert response.status_code == 503
    assert_matches(response, "getRealtimeToken")


async def test_token_is_for_the_personal_channel(rt_client: httpx.AsyncClient) -> None:
    me = await sign_in(rt_client)
    response = await rt_client.post("/realtime/token", headers=me.headers)
    assert response.status_code == 200
    assert_matches(response, "getRealtimeToken")
    body = response.json()
    assert body["channel"] == f"personal:#{me.user_id}"
    claims = jwt.decode(body["token"], CENTRIFUGO_TOKEN_SECRET, algorithms=["HS256"])
    assert claims["sub"] == me.user_id
    expires = datetime.fromisoformat(body["expires_at"])
    assert 3500 < (expires - datetime.now(UTC)).total_seconds() <= 3600


async def test_disabled_realtime_publishes_nothing(settings: Settings) -> None:
    rt = Realtime(settings)
    assert not rt.enabled
    await rt.broadcast([uuid.uuid4()], {"type": "x"})  # no server, no error
    await rt.aclose()


async def test_failed_publish_is_retried_by_the_worker(
    rt_settings: Settings, database: Database
) -> None:
    require_centrifugo()
    user = uuid.uuid4()
    params = {"users": [str(user)], "n": 1}
    down = Realtime(_with_centrifugo(rt_settings, "http://127.0.0.1:9/api"))
    async with database.sessionmaker() as session:
        await app_realtime.publish(session, down, TEST_KIND, params)
    async with database.sessionmaker() as session:
        job = await session.scalar(select(Job).where(Job.kind == app_realtime.PUBLISH_JOB))
        assert job is not None
        assert job.payload == {"kind": TEST_KIND, "params": params}

    up = Realtime(rt_settings)
    token = jwt.encode({"sub": str(user)}, CENTRIFUGO_TOKEN_SECRET, algorithm="HS256")
    ws_url = rt_settings.centrifugo_public_url
    async with centrifugo_client(ws_url, token) as cf:
        sub = await cf.call("subscribe", {"channel": personal_channel(user)})
        assert "subscribe" in sub, sub
        worker = build_worker(rt_settings, database, realtime_client=up)
        assert await worker.run_one()
        push = await cf.push()
        assert push["pub"]["data"] == {"type": "test.ping", "n": 1}
    await up.aclose()
    await down.aclose()


async def test_broadcast_reaches_only_the_own_channel_and_recovers(
    rt_client: httpx.AsyncClient, rt_settings: Settings
) -> None:
    require_centrifugo()
    alice = await sign_in(rt_client, 2001, "Алиса")
    bob = await sign_in(rt_client, 2002, "Боб")
    token = (await rt_client.post("/realtime/token", headers=alice.headers)).json()
    rt = Realtime(rt_settings)

    async with centrifugo_client(token["url"], token["token"]) as cf:
        denied = await cf.call("subscribe", {"channel": f"personal:#{bob.user_id}"})
        assert denied["error"]["code"] == 103  # permission denied
        sub = (await cf.call("subscribe", {"channel": token["channel"], "recover": True}))[
            "subscribe"
        ]
        await rt.broadcast(
            [uuid.UUID(alice.user_id), uuid.UUID(bob.user_id)], {"type": "test.ping", "n": 1}
        )
        first = await cf.push()
        assert first["channel"] == token["channel"]
        assert first["pub"]["data"] == {"type": "test.ping", "n": 1}
        offset, epoch = first["pub"]["offset"], sub["epoch"]

    # Events published while the client was offline come back on resubscribe.
    await rt.broadcast([uuid.UUID(alice.user_id)], {"type": "test.ping", "n": 2})
    async with centrifugo_client(token["url"], token["token"]) as cf:
        resub = await cf.call(
            "subscribe",
            {"channel": token["channel"], "recover": True, "offset": offset, "epoch": epoch},
        )
        assert resub["subscribe"]["recovered"] is True
        assert [p["data"] for p in resub["subscribe"]["publications"]] == [
            {"type": "test.ping", "n": 2}
        ]
    await rt.aclose()


async def test_broadcast_raises_when_centrifugo_is_down(rt_settings: Settings) -> None:
    rt = Realtime(_with_centrifugo(rt_settings, "http://127.0.0.1:9/api"))
    with pytest.raises(RealtimeUnavailable):
        await rt.broadcast([uuid.uuid4()], {"type": "x"})
    await rt.aclose()


async def test_message_reaches_an_open_chat_within_a_second(
    rt_client: httpx.AsyncClient,
) -> None:
    require_centrifugo()
    alice = await sign_in(rt_client, 2001, "Алиса")
    bob = await sign_in(rt_client, 2002, "Боб")
    code = (await rt_client.post("/invites", headers=alice.headers)).json()["code"]
    await rt_client.post(f"/invites/{code}/accept", headers=bob.headers)
    conversation = (
        await rt_client.post(
            "/conversations/direct", json={"user_id": alice.user_id}, headers=bob.headers
        )
    ).json()
    token = (await rt_client.post("/realtime/token", headers=bob.headers)).json()

    async with centrifugo_client(token["url"], token["token"]) as cf:
        await cf.call("subscribe", {"channel": token["channel"], "recover": True})
        started = time.monotonic()
        sent = await rt_client.post(
            f"/conversations/{conversation['id']}/messages",
            json={"text": "привет", "client_id": str(uuid.uuid4())},
            headers=alice.headers,
        )
        push = await cf.push(timeout=1.0)
        elapsed = time.monotonic() - started

    assert sent.status_code == 201
    event = push["pub"]["data"]
    assert event["type"] == "message.created"
    assert event["message"]["id"] == sent.json()["id"]
    assert event["message"]["text"] == "привет"
    assert elapsed < 1.0
