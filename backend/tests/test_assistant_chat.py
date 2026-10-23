"""The day chat with the assistant (M6, ADR 0013)."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from ayda.app import assistant_chat, privacy
from ayda.core.db import Database
from ayda.modules.analytics.models import Event
from ayda.modules.assistant import FakeProvider
from ayda.modules.assistant import chat as chat_store
from ayda.modules.assistant.models import ChatMessage
from tests.contract import assert_matches
from tests.helpers import SignedIn
from tests.test_day import checkin, forecast, onboarded, use_tools


def answer(reply: str, action: dict[str, Any] | None = None) -> str:
    return json.dumps({"reply": reply, "action": action}, ensure_ascii=False)


async def send(
    client: httpx.AsyncClient, user: SignedIn, text: str, quest_id: str | None = None
) -> httpx.Response:
    body: dict[str, Any] = {"text": text}
    if quest_id:
        body["quest_id"] = quest_id
    return await client.post("/assistant/messages", json=body, headers=user.headers)


async def topic(
    client: httpx.AsyncClient, user: SignedIn, quest_id: str | None = None
) -> dict[str, Any]:
    params = {"quest_id": quest_id} if quest_id else {}
    response = await client.get("/assistant/messages", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    assert_matches(response, "listAssistantMessages")
    return response.json()


async def checked_in(
    app: FastAPI, client: httpx.AsyncClient, text: str = "", telegram_id: int = 1001
) -> SignedIn:
    use_tools(app, [FakeProvider()], forecast())
    user = await onboarded(client, telegram_id)
    await checkin(client, user, text)
    return user


async def test_the_check_in_opens_the_day_chat(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await checked_in(app, client, "Работа до 18, вечером свободен")
    chat = await topic(client, user)
    assert [(m["role"], m["source"]) for m in chat["items"]] == [
        ("user", None),
        ("assistant", "code"),
    ]
    assert chat["items"][0]["text"] == "Работа до 18, вечером свободен"
    assert chat["items"][1]["text"] == chat_store.REPLY_CHECKIN
    assert chat["messages_left"] == assistant_chat.DAILY_LIMIT - 1

    # An empty check-in only gets the assistant's line.
    other = await checked_in(app, client, telegram_id=2002)
    assert [m["text"] for m in (await topic(client, other))["items"]] == [
        chat_store.REPLY_EMPTY_CHECKIN
    ]


async def test_the_assistant_answers_with_the_topic_and_no_personal_data(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    user = await checked_in(app, client, "Сдать отчёт")
    llm = FakeProvider(answers=[answer("Попробуй сделать перерыв на прогулку после обеда.")])
    use_tools(app, [llm], forecast())

    response = await send(client, user, "Как не выгореть к вечеру?")
    assert response.status_code == 201, response.text
    assert_matches(response, "sendAssistantMessage")
    body = response.json()
    assert body["sent"]["text"] == "Как не выгореть к вечеру?"
    assert body["reply"]["source"] == "llm" and body["reply"]["cards"] == []
    assert body["reply"]["text"].startswith("Попробуй")
    assert body["messages_left"] == assistant_chat.DAILY_LIMIT - 2

    [(_, prompt)] = llm.calls
    sent = json.loads(prompt)
    assert [m["text"] for m in sent["messages"]] == [
        "Сдать отчёт",
        chat_store.REPLY_CHECKIN,
        "Как не выгореть к вечеру?",
    ]
    assert sent["profile"]["goals"] == ["more_movement"] and sent["quest"] is None
    assert sent["today_quests"]
    assert "Саша" not in prompt and "Калининград" not in prompt

    async with database.sessionmaker() as session:
        [logged] = list(
            await session.scalars(select(Event).where(Event.type == "assistant_message"))
        )
    assert logged.payload["topic"] == "day" and logged.payload["source"] == "llm"
    assert "выгореть" not in json.dumps(logged.payload, ensure_ascii=False)
    assert len((await topic(client, user))["items"]) == 4


async def test_a_quest_has_its_own_topic(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await checked_in(app, client)
    day = (await client.get("/days/today", headers=user.headers)).json()
    quest = day["quests"][0]
    llm = FakeProvider(answers=[answer("Можно взять с собой друга.")])
    use_tools(app, [llm], forecast())

    response = await send(client, user, "Как разнообразить?", quest["id"])
    assert response.status_code == 201, response.text
    assert response.json()["reply"]["quest_id"] == quest["id"]
    sent = json.loads(llm.calls[0][1])
    assert sent["quest"]["title"] == quest["title"]
    assert [m["text"] for m in sent["messages"]] == ["Как разнообразить?"]

    quest_topic = await topic(client, user, quest["id"])
    assert [m["role"] for m in quest_topic["items"]] == ["user", "assistant"]
    assert len((await topic(client, user))["items"]) == 1  # the day topic is apart

    missing = await send(client, user, "Привет", str(uuid.uuid4()))
    assert missing.status_code == 404
    assert missing.json()["type"].endswith("/quest-not-found")


async def test_a_broken_answer_falls_back_to_code(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await checked_in(app, client)
    # A link in the reply is a fact the model must not write: retry, then code.
    bad = answer("Загляни на https://example.ru, там всё есть.")
    use_tools(app, [FakeProvider(answers=[bad, bad])], forecast())
    reply = (await send(client, user, "Где поужинать сегодня?")).json()["reply"]
    assert reply["source"] == "code"
    assert reply["text"] == "Вот места, где можно поесть."

    use_tools(app, [FakeProvider()], forecast())
    other = (await send(client, user, "Расскажи анекдот")).json()["reply"]
    assert other["text"] == assistant_chat.REPLY_UNAVAILABLE


def test_code_understands_the_obvious_requests() -> None:
    def action(text: str) -> tuple[str | None, str | None]:
        found = assistant_chat.code_answer(text).action
        return (found.type, found.kind) if found else (None, None)

    assert action("Что приготовить из курицы и риса?") == ("suggest_dishes", None)
    assert action("Хочу в бар вечером") == ("find_places", "drinks")
    assert action("Где можно погулять?") == ("find_places", "walk")
    assert action("Посоветуй кафе") == ("find_places", "food")
    assert action("Как дела?") == (None, None)


async def test_the_daily_limit(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assistant_chat, "DAILY_LIMIT", 2)
    user = await checked_in(app, client)
    use_tools(app, [FakeProvider()], forecast())
    assert (await send(client, user, "Раз")).status_code == 201
    assert (await send(client, user, "Два")).json()["messages_left"] == 0
    over = await send(client, user, "Три")
    assert over.status_code == 429 and over.json()["type"].endswith("/assistant-limit")
    assert (await topic(client, user))["messages_left"] == 0


async def test_chats_of_finished_days_are_deleted(
    client: httpx.AsyncClient, database: Database
) -> None:
    user = await onboarded(client)
    owner = uuid.UUID(user.user_id)
    now = datetime.now(UTC)
    async with database.sessionmaker() as session:
        today = date.today()
        for day in (today - timedelta(days=3), today + timedelta(days=1)):
            await chat_store.add_message(session, owner, day, None, "user", "старое", now)
        await session.commit()
        assert await privacy.purge_old_assistant_chats(session, now) == 1
        await session.commit()
        left = list(await session.scalars(select(ChatMessage.local_date)))
    assert left == [today + timedelta(days=1)]
