"""Assistant chat actions (M6, ADR 0013): places to walk or eat, dishes from what is at
home, a new quest. The LLM only asks; code builds every fact on a card."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select, update

from ayda.app import assistant_chat
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import events
from ayda.modules.assistant import FakeProvider, recipes
from ayda.modules.auth import User
from tests import test_events
from tests.contract import assert_matches
from tests.test_assistant_chat import answer, checked_in, send, topic
from tests.test_day import forecast, use_tools
from tests.test_venues import KALININGRAD, NOW, PAYLOAD, Overpass, ok


def walk_payload() -> dict[str, Any]:
    elements = [
        {
            "type": "way",
            "id": 101,
            "center": {"lat": 54.721, "lon": 20.511},
            "tags": {"leisure": "park", "name": "Центральный парк"},
        },
        {
            "type": "node",
            "id": 102,
            "lat": 54.705,
            "lon": 20.52,
            "tags": {"tourism": "viewpoint", "name": "Видовая площадка"},
        },
        {
            "type": "way",
            "id": 103,
            "center": {"lat": 54.70, "lon": 20.50},
            "tags": {"highway": "footway", "name": "Набережная Ветеранов"},
        },
        {
            "type": "way",
            "id": 104,
            "center": {"lat": 54.701, "lon": 20.501},
            "tags": {"highway": "footway", "name": "Набережная Ветеранов"},
        },
        {
            "type": "way",
            "id": 105,
            "center": {"lat": 54.71, "lon": 20.51},
            "tags": {"highway": "residential", "name": "Ленинский проспект"},
        },
    ]
    return {"elements": [*PAYLOAD["elements"], *elements]}


def test_walk_places_are_parsed_and_an_embankment_is_kept_once() -> None:
    parsed = {v.osm_id: v.kind for v in events.parse_venues(walk_payload())}
    assert parsed[101] == "park" and parsed[102] == "viewpoint" and parsed[103] == "embankment"
    assert 104 not in parsed and 105 not in parsed


async def test_the_query_asks_for_walk_places_too() -> None:
    overpass = Overpass(ok())
    await overpass.source().fetch(54.71, 20.51, 7000)
    body = httpx.QueryParams(overpass.requests[0].content.decode())["data"]
    assert '"leisure"~"^(park|garden)$"' in body and '"tourism"="viewpoint"' in body
    assert '"place"="square"' in body and '"name"~"набережная",i' in body


def test_ingredients_named_in_free_text_match_the_catalog() -> None:
    rb = recipes.book()
    found = recipes.match_ingredients(rb, ["есть курица, картошка и помидоры"])
    assert {"potato", "tomato", "chicken_fillet"} <= set(found)
    assert recipes.match_ingredients(rb, ["молоко"]) == ["milk"]  # not ground pepper
    assert recipes.match_ingredients(rb, ["пульт от телевизора"]) == []
    dishes = recipes.dishes_from(rb, found)
    assert dishes and dishes[0].have >= 2
    assert all(d.have >= 1 for d in dishes)


async def map_loaded(database: Database) -> None:
    source = Overpass(httpx.Response(200, json=walk_payload())).source()
    async with database.sessionmaker() as session:
        await events.load_venues(session, source, [KALININGRAD], 7000, NOW)
        await session.commit()


async def test_places_for_a_walk_come_from_code(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    await map_loaded(database)
    user = await checked_in(app, client)
    day = (await client.get("/days/today", headers=user.headers)).json()
    walk = {"type": "find_places", "kind": "walk"}
    use_tools(app, [FakeProvider(answers=[answer("Вот куда можно сходить.", walk)])], forecast())

    response = await send(client, user, "Куда пойти гулять?", day["quests"][0]["id"])
    assert response.status_code == 201, response.text
    assert_matches(response, "sendAssistantMessage")
    [card] = response.json()["reply"]["cards"]
    assert card["kind"] == "places" and card["attribution"] == events.ATTRIBUTION
    kinds = {p["kind"] for p in card["places"]}
    assert kinds == {"park", "viewpoint", "embankment"}
    assert all(p["gis_url"].startswith("https://2gis.ru/") for p in card["places"])

    # The card is kept with the message.
    stored = (await topic(client, user, day["quests"][0]["id"]))["items"][-1]
    assert stored["cards"] == [card]

    # Without the LLM the same request still gets food places from code.
    use_tools(app, [FakeProvider()], forecast())
    food = (await send(client, user, "Где поужинать?")).json()["reply"]
    assert food["source"] == "code"
    assert {p["kind"] for p in food["cards"][0]["places"]} <= {"restaurant", "cafe", "fast_food"}


async def test_no_city_or_no_places_is_said_on_the_card(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    user = await checked_in(app, client)
    use_tools(app, [FakeProvider()], forecast())
    [card] = (await send(client, user, "Где погулять?")).json()["reply"]["cards"]
    assert card["places"] == [] and card["note"] == assistant_chat.NOTE_LOADING
    async with database.sessionmaker() as session:
        [job] = list(await session.scalars(select(Job).where(Job.kind == "events.venues")))
        assert job.payload["city_id"] == KALININGRAD and job.status == "queued"
    # Asking again the same day does not queue a second load.
    await send(client, user, "Где погулять?")
    async with database.sessionmaker() as session:
        assert len(list(await session.scalars(select(Job).where(Job.kind == "events.venues")))) == 1

    # A load of an empty map counts as loaded: then the card says there is little there.
    source = Overpass(httpx.Response(200, json={"elements": []})).source()
    async with database.sessionmaker() as session:
        await events.load_venues(session, source, [KALININGRAD], 7000, NOW)
        await session.commit()
    [card] = (await send(client, user, "Где погулять?")).json()["reply"]["cards"]
    assert card["note"] == assistant_chat.NOTE_NO_PLACES

    async with database.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(user.user_id)).values(city_id=None)
        )
        await session.commit()
    [card] = (await send(client, user, "Где погулять?")).json()["reply"]["cards"]
    assert card["note"] == assistant_chat.NOTE_NO_CITY


async def test_dishes_from_what_is_at_home(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await checked_in(app, client)
    cook = {"type": "suggest_dishes", "ingredients": ["курица", "картошка"], "meal": "dinner"}
    use_tools(app, [FakeProvider(answers=[answer("Есть пара идей на ужин.", cook)])], forecast())
    response = await send(client, user, "Что приготовить на ужин?")
    assert_matches(response, "sendAssistantMessage")
    [card] = response.json()["reply"]["cards"]
    assert card["kind"] == "dishes" and card["note"] == assistant_chat.NOTE_ALLERGENS
    assert 1 <= len(card["recipes"]) <= assistant_chat.DISHES_SHOWN
    assert card["recipes"][0]["why"].startswith("Есть дома: 2 из")
    assert all(r["id"] in recipes.book().recipes for r in card["recipes"])

    # Code reads the products from the text when there is no LLM.
    use_tools(app, [FakeProvider()], forecast())
    [card] = (await send(client, user, "Что приготовить из яиц и молока?")).json()["reply"]["cards"]
    assert card["recipes"] and card["recipes"][0]["why"].startswith("Есть дома:")

    unknown = {"type": "suggest_dishes", "ingredients": ["пульт"]}
    use_tools(app, [FakeProvider(answers=[answer("Посмотрим.", unknown)])], forecast())
    [card] = (await send(client, user, "Что приготовить?")).json()["reply"]["cards"]
    assert card["note"] == assistant_chat.NOTE_UNKNOWN_FOOD and card["recipes"]


async def test_a_new_quest_is_offered_for_today(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await checked_in(app, client)
    idea = {
        "type": "suggest_quest",
        "title": "Пройти 3 км по набережной",
        "category": "walk",
        "duration_min": 45,
    }
    use_tools(app, [FakeProvider(answers=[answer("Вот квест.", idea)] * 3)], forecast())
    [card] = (await send(client, user, "Придумай квест")).json()["reply"]["cards"]
    quest = card["quest"]
    assert quest["state"] == "offered" and quest["source"] == "custom"
    assert quest["title"] == idea["title"] and quest["why"] == assistant_chat.WHY_QUEST

    day = (await client.get("/days/today", headers=user.headers)).json()
    assert quest["id"] in [q["id"] for q in day["quests"]]
    taken = await client.post(f"/day-quests/{quest['id']}/take", headers=user.headers)
    assert taken.status_code == 200, taken.text


async def test_offered_ideas_are_capped(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(assistant_chat, "MAX_OFFERED", 1)
    user = await checked_in(app, client)
    idea = {"type": "suggest_quest", "title": "Растяжка", "category": "walk", "duration_min": 10}
    use_tools(app, [FakeProvider(answers=[answer("Вот.", idea)] * 2)], forecast())
    assert await send(client, user, "Ещё квест")
    [card] = (await send(client, user, "И ещё")).json()["reply"]["cards"]
    assert card["quest"] is None and card["note"] == assistant_chat.NOTE_TOO_MANY


async def test_a_quest_title_with_a_link_is_rejected(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    user = await checked_in(app, client)
    bad = {
        "type": "suggest_quest",
        "title": "Зайди на site.ru",
        "category": "rest",
        "duration_min": 20,
    }
    use_tools(app, [FakeProvider(answers=[answer("Вот.", bad)] * 2)], forecast())
    reply = (await send(client, user, "Придумай квест")).json()["reply"]
    assert reply["source"] == "code" and reply["cards"] == []


def soon(source_id: str, hours: float, title: str, city_id: int = 435, region: str = "39") -> Any:
    """A listing relative to the real clock: the chat itself uses the real time."""
    start = datetime.now(UTC) + timedelta(hours=hours)
    item = test_events.listing(source_id, timedelta(), city_id, region, title=title)
    return replace(item, starts_at=start, ends_at=start + timedelta(hours=2))


async def test_events_are_found_across_the_region_by_interest(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    await test_events.seed(
        database,
        [
            soon("fair", 3, "Ярмарка мёда"),
            soon("lecture", 5, "Лекция о море"),
            soon("jazz", 30, "Джазовый вечер", test_events.SOVETSK),
            soon("rock", 26, "Рок-концерт", test_events.SVETLOGORSK),
            soon("moscow", 4, "Джаз в Москве", test_events.MOSCOW, "77"),
        ],
        datetime.now(UTC),
    )
    user = await checked_in(app, client)
    find = {"type": "find_events", "query": "джаз"}
    use_tools(app, [FakeProvider(answers=[answer("Вот что нашёл.", find)])], forecast())

    response = await send(client, user, "Хочу на джаз")
    assert response.status_code == 201, response.text
    assert_matches(response, "sendAssistantMessage")
    [card] = response.json()["reply"]["cards"]
    assert card["kind"] == "events" and card["attribution"] == assistant_chat.EVENTS_ATTRIBUTION
    titles = [e["title"] for e in card["events"]]
    assert titles[0] == "Джазовый вечер" and "Джаз в Москве" not in titles
    assert len(titles) == 4 and card["note"] is None
    assert card["events"][0]["city"] == "Советск" and card["events"][0]["distance_km"] > 50

    # A town of the region narrows the search to it.
    there = {"type": "find_events", "place": "Светлогорск"}
    use_tools(app, [FakeProvider(answers=[answer("Смотрю.", there)])], forecast())
    [card] = (await send(client, user, "Что будет в Светлогорске?")).json()["reply"]["cards"]
    assert card["events"][0]["title"] == "Рок-концерт"

    # Nothing like it: the card says so and shows what else is on.
    opera = {"type": "find_events", "query": "опера"}
    use_tools(app, [FakeProvider(answers=[answer("Смотрю.", opera)])], forecast())
    [card] = (await send(client, user, "Хочу в оперу")).json()["reply"]["cards"]
    assert card["note"] == assistant_chat.NOTE_NOT_EXACT and card["events"]

    # Another region is not loaded.
    far = {"type": "find_events", "place": "Москва"}
    use_tools(app, [FakeProvider(answers=[answer("Смотрю.", far)])], forecast())
    [card] = (await send(client, user, "Что в Москве?")).json()["reply"]["cards"]
    assert card["note"] == assistant_chat.NOTE_OTHER_REGION and card["events"] == []

    # Without the LLM code reads the request.
    use_tools(app, [FakeProvider()], forecast())
    reply = (await send(client, user, "Какие концерты будут?")).json()["reply"]
    assert reply["source"] == "code" and reply["cards"][0]["events"][0]["title"] == "Рок-концерт"


async def test_no_events_is_said_on_the_card(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await checked_in(app, client)
    use_tools(app, [FakeProvider()], forecast())
    [card] = (await send(client, user, "Куда сходить вечером? Есть афиша?")).json()["reply"][
        "cards"
    ]
    assert card["kind"] == "events" and card["note"] == assistant_chat.NOTE_NO_EVENTS
