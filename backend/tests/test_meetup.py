"""«Айда, организуй»: a meetup from the last messages of a chat (M5)."""

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from ayda.core.db import Database
from ayda.modules import events
from ayda.modules.analytics.models import Event
from ayda.modules.assistant import FakeProvider, ProviderError
from tests.conftest import FakeRealtime
from tests.contract import assert_matches
from tests.helpers import SignedIn
from tests.test_day import TZ, forecast, onboarded, use_tools
from tests.test_feed import befriend
from tests.test_venues import PAYLOAD, Overpass, node, ok

TODAY = datetime.now(ZoneInfo(TZ)).date()
NOW = datetime.combine(TODAY, time(10, 0), ZoneInfo(TZ)).astimezone(UTC)
KALININGRAD = 435


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr("ayda.api.chat._now", lambda: NOW)
    monkeypatch.setattr("ayda.api.coop._now", lambda: NOW)
    return NOW


def intent(**fields: Any) -> str:
    base: dict[str, Any] = {"kind": "venue", "venue_kinds": ["cafe"], "time": "18:30"}
    return json.dumps(base | fields)


async def chat_between(
    client: httpx.AsyncClient,
    database: Database,
    *texts: str,
    payload: dict[str, Any] | None = None,
) -> tuple[SignedIn, SignedIn, str]:
    alice = await onboarded(client, 1001)
    bob = await onboarded(client, 2002)
    await befriend(client, alice, bob)
    conversation = (
        await client.post(
            "/conversations/direct", json={"user_id": bob.user_id}, headers=alice.headers
        )
    ).json()["id"]
    for text in texts:
        sent = await client.post(
            f"/conversations/{conversation}/messages",
            json={"text": text, "client_id": str(uuid.uuid4())},
            headers=bob.headers,
        )
        assert sent.status_code == 201, sent.text
    async with database.sessionmaker() as session:
        await events.load_venues(
            session, Overpass(ok(payload or PAYLOAD)).source(), [KALININGRAD], 7000, NOW
        )
        await session.commit()
    return alice, bob, conversation


async def suggest(client: httpx.AsyncClient, user: SignedIn, conversation: str) -> httpx.Response:
    return await client.post(f"/conversations/{conversation}/meetup", headers=user.headers)


async def test_the_assistant_reads_the_chat_and_code_picks_the_venues(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = FakeProvider(answers=[intent()])
    use_tools(app, [llm], forecast())
    alice, _, conversation = await chat_between(
        client, database, "Го в кафе?", "Давай в 18:30 в центре"
    )

    response = await suggest(client, alice, conversation)
    assert response.status_code == 200, response.text
    assert_matches(response, "suggestMeetup")
    offer = response.json()
    assert offer["kind"] == "venue" and offer["source"] == "llm"
    assert datetime.fromisoformat(offer["starts_at"]) == datetime.combine(
        TODAY, time(18, 30), ZoneInfo(TZ)
    )
    # Only a cafe fits; the unknown hours do not exclude it, a closed one would.
    names = [v["name"] for v in offer["venues"]]
    assert names == ["Кофейня на углу"]
    venue = offer["venues"][0]
    assert venue["address"] == "Ленина, 1" and venue["open_now"] is None
    assert venue["osm_url"].startswith("https://www.openstreetmap.org/node/")
    assert venue["gis_url"].startswith("https://2gis.ru/search/")
    assert venue["yandex_url"].startswith("https://yandex.ru/maps/?text=")
    assert offer["attribution"] == "© OpenStreetMap contributors"

    # The model got only the texts of the chat: no names, no ids.
    [(_, user_prompt)] = llm.calls
    assert json.loads(user_prompt) == {"messages": ["Го в кафе?", "Давай в 18:30 в центре"]}
    assert "Алиса" not in user_prompt and "Боря" not in user_prompt
    async with database.sessionmaker() as session:
        [logged] = list(
            await session.scalars(select(Event).where(Event.type == "meetup_suggested"))
        )
        assert logged.payload["venues"] == 1 and logged.payload["messages"] == 2
        assert "кафе" not in json.dumps(logged.payload, ensure_ascii=False)


async def test_only_the_last_eight_messages_are_sent_and_only_to_members(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = FakeProvider(answers=[intent(kind="unclear", venue_kinds=[], time=None)])
    use_tools(app, [llm], forecast())
    texts = [f"сообщение {i}" for i in range(12)]
    alice, _, conversation = await chat_between(client, database, *texts)
    outsider = await onboarded(client, 3003)
    assert (await suggest(client, outsider, conversation)).status_code == 404

    offer = (await suggest(client, alice, conversation)).json()
    assert offer["kind"] == "unclear" and offer["venues"] == [] and offer["note"]
    assert json.loads(llm.calls[0][1])["messages"] == texts[-8:]


async def test_without_the_assistant_code_suggests_cafes_in_the_evening(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    use_tools(app, [FakeProvider(answers=[ProviderError("rate_limited")])], forecast())
    alice, _, conversation = await chat_between(client, database, "увидимся?")
    offer = (await suggest(client, alice, conversation)).json()
    assert offer["source"] == "code" and offer["kind"] == "venue"
    assert datetime.fromisoformat(offer["starts_at"]) == datetime.combine(
        TODAY, time(19, 0), ZoneInfo(TZ)
    )
    assert [v["name"] for v in offer["venues"]] == ["Кофейня на углу", "Ресторан у моря"]


async def test_an_online_meetup_has_no_venues_and_needs_an_activity(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = FakeProvider(
        answers=[
            intent(kind="online", venue_kinds=[], activity=None),  # invalid: retried
            intent(kind="online", venue_kinds=[], activity="Дота вдвоём", time=None),
        ]
    )
    use_tools(app, [llm], forecast())
    alice, _, conversation = await chat_between(client, database, "погамаем вечером?")
    offer = (await suggest(client, alice, conversation)).json()
    assert offer["kind"] == "online" and offer["activity"] == "Дота вдвоём"
    assert offer["venues"] == [] and offer["attribution"] is None and offer["starts_at"]


async def test_too_late_for_today_and_no_venues_in_a_small_town(
    app: FastAPI, client: httpx.AsyncClient, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_tools(
        app, [FakeProvider(answers=[intent(venue_kinds=["pub"]), intent(time="23:30")])], forecast()
    )
    alice, _, conversation = await chat_between(client, database, "пиво?")
    empty = (await suggest(client, alice, conversation)).json()
    assert empty["venues"] == [] and empty["note"] and empty["attribution"] is None

    late = datetime.combine(TODAY + timedelta(days=1), time(3, 20), ZoneInfo(TZ)).astimezone(UTC)
    monkeypatch.setattr("ayda.api.chat._now", lambda: late)
    too_late = (await suggest(client, alice, conversation)).json()
    assert too_late["starts_at"] is None and "поздно" in too_late["note"]


async def test_picking_a_venue_creates_the_coop_with_its_place(
    app: FastAPI, client: httpx.AsyncClient, database: Database, realtime: FakeRealtime
) -> None:
    use_tools(app, [FakeProvider(answers=[intent()])], forecast())
    alice, bob, conversation = await chat_between(client, database, "кофе в 18:30?")
    offer = (await suggest(client, alice, conversation)).json()
    venue = offer["venues"][0]

    picked = await client.post(
        f"/conversations/{conversation}/meetup/pick",
        json={"venue_id": venue["id"], "starts_at": offer["starts_at"]},
        headers=alice.headers,
    )
    assert picked.status_code == 201, picked.text
    assert_matches(picked, "pickMeetup")
    coop = picked.json()
    assert coop["kind"] == "same" and coop["title"] == "Встреча: Кофейня на углу"
    assert coop["place"]["source_id"] == "node/1" and coop["place"]["lat"] == 54.71
    assert datetime.fromisoformat(coop["starts_at"]) == datetime.fromisoformat(offer["starts_at"])
    assert [(p["user"]["first_name"], p["status"]) for p in coop["participants"]] == [
        ("Саша", "owner"),
        ("Саша", "invited"),
    ]
    assert coop["my_quest_id"]
    seen = await client.get(f"/coops/{coop['id']}", headers=bob.headers)
    assert (
        seen.json()["place"]["name"] == "Кофейня на углу" and seen.json()["my_status"] == "invited"
    )


async def test_picking_rules(app: FastAPI, client: httpx.AsyncClient, database: Database) -> None:
    use_tools(app, [], forecast())
    alice, _, conversation = await chat_between(client, database, "привет")
    url = f"/conversations/{conversation}/meetup/pick"
    start = (NOW + timedelta(hours=8)).isoformat()
    cases: list[tuple[dict[str, Any], int]] = [
        ({"starts_at": start}, 422),
        ({"venue_id": 1, "activity": "Дота", "starts_at": start}, 422),
        ({"venue_id": 999999, "starts_at": start}, 404),
        ({"activity": "Дота", "starts_at": (NOW + timedelta(days=2)).isoformat()}, 422),
    ]
    for body, status in cases:
        response = await client.post(url, json=body, headers=alice.headers)
        assert response.status_code == status, (body, response.text)
        assert_matches(response, "pickMeetup")
    online = await client.post(
        url, json={"activity": "Дота вдвоём", "starts_at": start}, headers=alice.headers
    )
    assert online.status_code == 201
    assert online.json()["title"] == "Онлайн: Дота вдвоём" and online.json()["place"] is None


def with_places(*elements: dict[str, Any]) -> dict[str, Any]:
    return {"elements": [*PAYLOAD["elements"], *elements]}


PARK = {
    "type": "way",
    "id": 20,
    "center": {"lat": 54.72, "lon": 20.5},
    "tags": {"leisure": "park", "name": "Центральный парк"},
}


async def test_a_place_named_in_the_chat_comes_first(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = FakeProvider(
        answers=[intent(venue_kinds=["restaurant"], place_name="Ростерхит", time="19:00")]
    )
    use_tools(app, [llm], forecast())
    payload = with_places(node(30, "Roasterhit", "restaurant"))
    alice, _, conversation = await chat_between(
        client, database, "Пошли в ресторан Ростерхит", payload=payload
    )
    response = await suggest(client, alice, conversation)
    assert_matches(response, "suggestMeetup")
    offer = response.json()
    assert offer["venues"][0]["name"] == "Roasterhit"
    assert offer["note"] is None
    assert "Ресторан у моря" in [v["name"] for v in offer["venues"]]


async def test_an_unknown_named_place_is_said_so_and_similar_ones_follow(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = FakeProvider(answers=[intent(venue_kinds=["restaurant"], place_name="Тратторияна")])
    use_tools(app, [llm], forecast())
    alice, _, conversation = await chat_between(client, database, "Пошли в Тратторияна")
    offer = (await suggest(client, alice, conversation)).json()
    assert "Тратторияна" in offer["note"]
    assert [v["name"] for v in offer["venues"]] == ["Ресторан у моря"]


async def test_the_latest_intent_wins_a_walk_in_a_park_at_three(
    app: FastAPI, client: httpx.AsyncClient, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = FakeProvider(answers=[intent(venue_kinds=["park"], time="15:00")])
    use_tools(app, [llm], forecast())
    alice, _, conversation = await chat_between(
        client,
        database,
        "го в ресторан?",
        "пошли погуляем в парк в 15:00",
        payload=with_places(PARK),
    )
    offer = (await suggest(client, alice, conversation)).json()
    assert [v["name"] for v in offer["venues"]] == ["Центральный парк"]
    assert offer["venues"][0]["kind"] == "park"
    assert datetime.fromisoformat(offer["starts_at"]) == datetime.combine(
        TODAY, time(15, 0), ZoneInfo(TZ)
    )


async def test_without_the_assistant_code_reads_the_latest_kind_and_time(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    use_tools(app, [FakeProvider(answers=[ProviderError("rate_limited")])], forecast())
    alice, _, conversation = await chat_between(
        client,
        database,
        "го в ресторан?",
        "лучше погуляем в парке в 15:00",
        payload=with_places(PARK),
    )
    offer = (await suggest(client, alice, conversation)).json()
    assert offer["source"] == "code"
    assert [v["name"] for v in offer["venues"]] == ["Центральный парк"]
    assert datetime.fromisoformat(offer["starts_at"]) == datetime.combine(
        TODAY, time(15, 0), ZoneInfo(TZ)
    )


def test_guessing_without_the_assistant() -> None:
    from ayda.modules.assistant import guess_meetup

    walk = guess_meetup(["го в ресторан", "пошли погуляем в парк к 16"])
    assert walk.venue_kinds == ["park"] and walk.time == "16:00"
    assert guess_meetup(["увидимся?"]).venue_kinds == []


def test_names_are_compared_across_alphabets() -> None:
    from ayda.modules.events.venues import name_score

    assert name_score("Ростерхит", "Roasterhit") >= 0.78
    assert name_score("ростер хит", "РОСТЕРХИТ") == 1.0
    assert name_score("Ростерхит", "Кофейня на углу") < 0.78
