import json
import uuid
from collections.abc import Iterator, Mapping
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.app import notifications
from ayda.app.notifications import Message
from ayda.core.db import Database
from ayda.core.push import FcmSender, InvalidToken, Push, PushRetryLater
from ayda.modules import auth
from ayda.modules.auth.models import Device
from tests.conftest import FakeMailer
from tests.contract import assert_matches
from tests.helpers import sign_in
from tests.test_bot import FakeSender
from tests.test_email_auth import email_session


class FakePush:
    def __init__(self, invalid: set[str] | None = None) -> None:
        self.sent: list[tuple[str, Push]] = []
        self.invalid = invalid or set()

    async def send(self, token: str, push: Push) -> None:
        if token in self.invalid:
            raise InvalidToken
        self.sent.append((token, push))


@pytest.fixture
def secret_kind() -> Iterator[str]:
    """A notice whose bot text has a name in it, like a DM notice."""

    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        return Message(f"Тебе пишет {user.first_name}")

    notifications.RENDERERS["chat.message"] = render
    yield "chat.message"
    del notifications.RENDERERS["chat.message"]


async def register(
    client: httpx.AsyncClient, headers: dict[str, str], token: str
) -> httpx.Response:
    return await client.put(
        "/me/devices", json={"platform": "android", "token": token}, headers=headers
    )


async def test_devices_register_move_and_remove(
    client: httpx.AsyncClient, database: Database
) -> None:
    sasha = await sign_in(client, 1001, "Саша")
    first = await register(client, sasha.headers, "tok-1")
    assert first.status_code == 200
    assert_matches(first, "registerMyDevice")
    again = await register(client, sasha.headers, "tok-1")
    assert again.json()["id"] == first.json()["id"]

    # Petya signs in on the same phone: the token now belongs to him.
    petya = await sign_in(client, 1002, "Петя")
    await register(client, petya.headers, "tok-1")
    async with database.sessionmaker() as s:
        [device] = (await s.scalars(select(Device))).all()
    assert str(device.user_id) == petya.user_id

    not_mine = await client.delete(f"/me/devices/{first.json()['id']}", headers=sasha.headers)
    assert not_mine.status_code == 404
    assert_matches(not_mine, "removeMyDevice")
    gone = await client.delete(f"/me/devices/{first.json()['id']}", headers=petya.headers)
    assert gone.status_code == 204


async def test_app_users_get_a_generic_push_instead_of_the_bot(
    client: httpx.AsyncClient, database: Database, secret_kind: str
) -> None:
    user = await sign_in(client, 1001, "Саша")
    await register(client, user.headers, "tok-1")
    await register(client, user.headers, "tok-gone")
    payload = {
        "user_id": user.user_id,
        "kind": secret_kind,
        "params": {"conversation_id": "c1", "message_id": 5},
    }
    bot, push = FakeSender(), FakePush(invalid={"tok-gone"})
    async with database.sessionmaker() as s:
        result = await notifications.send(s, bot, payload, push)
        await s.commit()
    assert result.sent
    assert bot.sent == []
    [(token, sent)] = push.sent
    assert token == "tok-1"
    assert "Саша" not in sent.title + sent.body
    assert sent.data == {"kind": "chat.message", "conversation_id": "c1", "message_id": "5"}
    async with database.sessionmaker() as s:
        tokens = list(await s.scalars(select(Device.token)))
    assert tokens == ["tok-1"]  # the dead token is forgotten


async def test_channel_choice(
    client: httpx.AsyncClient, database: Database, secret_kind: str
) -> None:
    user = await sign_in(client, 1001, "Саша")
    payload = {"user_id": user.user_id, "kind": secret_kind, "params": {}}
    bot, push = FakeSender(), FakePush()

    async with database.sessionmaker() as s:
        assert (await notifications.send(s, bot, payload, push)).sent  # no app: the bot
    assert len(bot.sent) == 1 and push.sent == []

    await register(client, user.headers, "tok-1")
    r = await client.patch(
        "/me/profile", json={"notification_channel": "telegram"}, headers=user.headers
    )
    assert r.status_code == 200
    assert_matches(r, "updateProfile")
    assert r.json()["notification_channel"] == "telegram"
    async with database.sessionmaker() as s:
        assert (await notifications.send(s, bot, payload, push)).sent
    assert len(bot.sent) == 2 and push.sent == []


async def test_email_user_without_app_gets_nothing(
    client: httpx.AsyncClient, database: Database, mailer: FakeMailer, secret_kind: str
) -> None:
    session = await email_session(client, mailer)
    user_id = session["user"]["id"]  # pyright: ignore[reportIndexIssue]
    payload = {"user_id": user_id, "kind": secret_kind, "params": {}}
    async with database.sessionmaker() as s:
        result = await notifications.send(s, FakeSender(), payload, FakePush())
    assert result.reason == "no-telegram"

    h = {"Authorization": f"Bearer {session['access_token']}"}
    await client.patch("/me/profile", json={"notification_channel": "push"}, headers=h)
    async with database.sessionmaker() as s:
        result = await notifications.send(s, FakeSender(), payload, FakePush())
    assert result.reason == "no-device"


def service_account() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "project_id": "ayda-test",
            "client_email": "push@ayda-test.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


async def test_fcm_sender() -> None:
    calls: list[httpx.Request] = []
    status = {"send": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at-1", "expires_in": 3600})
        return httpx.Response(status["send"], json={"error": {"status": "NOT_FOUND"}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = FcmSender(service_account(), http)
    await sender.send("tok-1", Push("Айда", "Новое сообщение", {"kind": "chat.message"}))
    await sender.send("tok-1", Push("Айда", "Ещё", {}))

    oauth, first, second = calls
    assertion = dict(httpx.QueryParams(oauth.content.decode()))["assertion"]
    claims = jwt.decode(assertion, options={"verify_signature": False})  # pyright: ignore[reportUnknownMemberType]
    assert claims["iss"] == "push@ayda-test.iam.gserviceaccount.com"
    assert first.url.path == "/v1/projects/ayda-test/messages:send"
    assert first.headers["Authorization"] == "Bearer at-1"
    body = json.loads(first.content)["message"]
    assert body["token"] == "tok-1" and body["data"] == {"kind": "chat.message"}
    assert second.headers["Authorization"] == "Bearer at-1"  # the access token is reused

    status["send"] = 404
    with pytest.raises(InvalidToken):
        await sender.send("tok-1", Push("Айда", "x"))
    status["send"] = 503
    with pytest.raises(PushRetryLater):
        await sender.send("tok-1", Push("Айда", "x"))
    _ = uuid
