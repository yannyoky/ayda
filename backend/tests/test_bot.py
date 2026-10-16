import time
import uuid
from collections.abc import Iterator, Mapping
from typing import Any

import httpx
import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.app import notifications
from ayda.app.notifications import Button, Message, RateLimiter, RetryLater, Unreachable
from ayda.bot import texts
from ayda.bot.handlers import start_reply
from ayda.bot.sender import AiogramSender, keyboard
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import auth
from ayda.worker import build_worker
from tests.helpers import sign_in


def test_start_greets_with_a_mini_app_button() -> None:
    plain = start_reply(Settings(), None)
    assert plain.text == texts.GREETING
    assert plain.button == Button(texts.OPEN_APP, "https://t.me/ayda_quest_bot?startapp")

    web = start_reply(Settings(miniapp_url="https://app.example/"), "")
    assert web.button is not None and web.button.web_app


def test_start_with_invite_code_passes_it_on() -> None:
    reply = start_reply(Settings(miniapp_url="https://app.example/"), "k3J9xQ2mLp0a")
    assert reply.text == texts.INVITE
    assert reply.button == Button(
        texts.OPEN_APP, "https://t.me/ayda_quest_bot?startapp=k3J9xQ2mLp0a"
    )
    assert start_reply(Settings(), "<script>").text == texts.GREETING


def test_keyboard() -> None:
    markup = keyboard(Message("hi", Button("Open", "https://app.example/", web_app=True)))
    assert markup is not None
    assert markup.inline_keyboard[0][0].web_app is not None
    assert keyboard(Message("hi")) is None


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[tuple[int, Message]] = []
        self.error = error

    async def send(self, chat_id: int, message: Message) -> None:
        if self.error:
            raise self.error
        self.sent.append((chat_id, message))


@pytest.fixture
def hello_kind() -> Iterator[str]:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        if params.get("skip"):
            return None
        return Message(f"Привет, {user.first_name}! {params['n']}")

    notifications.RENDERERS["test.hello"] = render
    yield "test.hello"
    del notifications.RENDERERS["test.hello"]


async def test_notify_goes_through_the_queue(
    client: httpx.AsyncClient, database: Database, settings: Settings, hello_kind: str
) -> None:
    user = await sign_in(client, 1001, "Саша")
    async with database.sessionmaker() as session:
        assert await notifications.notify(
            session, uuid.UUID(user.user_id), hello_kind, {"n": 3}, dedupe_key="hello:1"
        )
        assert not await notifications.notify(
            session, uuid.UUID(user.user_id), hello_kind, {"n": 3}, dedupe_key="hello:1"
        )
        await session.commit()
        [job] = list(await session.scalars(select(Job)))
    assert job.payload == {"user_id": user.user_id, "kind": hello_kind, "params": {"n": 3}}

    sender = FakeSender()
    assert await build_worker(settings, database, sender=sender).run_one()

    assert sender.sent == [(1001, Message("Привет, Саша! 3"))]


async def test_blocked_bot_marks_user_unreachable(
    client: httpx.AsyncClient, database: Database, hello_kind: str
) -> None:
    user = await sign_in(client, 1001, "Саша")
    payload = {"user_id": user.user_id, "kind": hello_kind, "params": {"n": 1}}

    async with database.sessionmaker() as session:
        result = await notifications.send(session, FakeSender(Unreachable()), payload)
        await session.commit()
    assert result.reason == "unreachable"

    sender = FakeSender()
    async with database.sessionmaker() as session:
        assert (await notifications.send(session, sender, payload)).reason == "unreachable"
        assert sender.sent == []
        await auth.mark_bot_reachable(session, 1001, True)
        skipped = await notifications.send(session, sender, payload | {"params": {"skip": True}})
        sent = await notifications.send(session, sender, payload)
    assert skipped.reason == "nothing-to-say" and sent.sent


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup: object = None) -> None:
        if self.error:
            raise self.error
        self.calls.append((chat_id, text))


async def test_aiogram_sender_maps_errors() -> None:
    method = SendMessage(chat_id=1, text="x")
    blocked = AiogramSender(FakeBot(TelegramForbiddenError(method, "Forbidden: bot was blocked")))  # pyright: ignore[reportArgumentType]
    slow = AiogramSender(FakeBot(TelegramRetryAfter(method, "Too Many Requests", 5)))  # pyright: ignore[reportArgumentType]

    with pytest.raises(Unreachable):
        await blocked.send(1, Message("x"))
    with pytest.raises(RetryLater):
        await slow.send(1, Message("x"))


async def test_rate_limiter_spaces_messages_to_one_chat() -> None:
    limiter = RateLimiter(per_second=1000, per_chat_s=0.05)
    start = time.monotonic()
    for _ in range(3):
        await limiter.wait(42)
    await limiter.wait(43)
    assert 0.09 <= time.monotonic() - start < 0.5
