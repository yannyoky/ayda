import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from ayda.app.day import DayTools
from ayda.core.db import Database
from ayda.modules.analytics.models import Event
from ayda.modules.assistant import Assistant, LLMProvider
from ayda.modules.events import WeatherClient
from tests.contract import assert_matches
from tests.helpers import SignedIn, sign_in

KALININGRAD = 435
TZ = "Europe/Kaliningrad"
SECRET_LINE = "Сдать отчёт Ивану Петрову"


def forecast(temp: float = 12, code: int = 1) -> dict[str, Any]:
    today = datetime.now(ZoneInfo(TZ)).date()
    hours = [datetime(today.year, today.month, today.day) + timedelta(hours=h) for h in range(48)]
    return {
        "hourly": {
            "time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours],
            "temperature_2m": [temp] * 48,
            "weather_code": [code] * 48,
            "wind_speed_10m": [2] * 48,
            "precipitation_probability": [0] * 48,
        }
    }


def weather_client(payload: dict[str, Any]) -> WeatherClient:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    return WeatherClient(httpx.AsyncClient(transport=transport))


class ScriptedLLM:
    """Parses the check-in into one task and ranks a rest quest first, then the next four."""

    name = "fake"
    model = "fake-1"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, system: str, user: str, timeout_s: float) -> str:
        self.prompts.append(user)
        data = json.loads(user)
        if "candidates" not in data:
            task = {"title": "Сдать отчёт", "category": "project", "duration_min": 60, "at": None}
            return json.dumps({"tasks": [task], "busy": ["09:00-18:00"], "free_evening": True})
        candidates = data["candidates"]
        rest = [c["id"] for c in candidates if c["category"] == "rest"][:1]
        others = [c["id"] for c in candidates if c["id"] not in rest][: 5 - len(rest)]
        items = [{"id": i, "why": "Подходит тебе сегодня"} for i in rest + others]
        return json.dumps({"items": items}, ensure_ascii=False)


def use_tools(app: FastAPI, providers: list[LLMProvider], weather: dict[str, Any]) -> None:
    app.state.day_tools = DayTools(
        assistant=Assistant(providers, sessionmaker=app.state.db.sessionmaker),
        weather=weather_client(weather),
    )


async def onboarded(client: httpx.AsyncClient, telegram_id: int = 1001) -> SignedIn:
    user = await sign_in(client, telegram_id)
    response = await client.patch(
        "/me/profile", json={"city_id": KALININGRAD}, headers=user.headers
    )
    assert response.status_code == 200
    await client.put("/me/goals", json={"goal_codes": ["more_movement"]}, headers=user.headers)
    return user


async def checkin(
    client: httpx.AsyncClient, user: SignedIn, text: str = "", mood: str = "normal"
) -> dict[str, Any]:
    response = await client.put(
        "/days/today/checkin", json={"text": text, "mood": mood}, headers=user.headers
    )
    assert response.status_code == 202, response.text
    assert_matches(response, "submitCheckin")
    return response.json()


def offered(day: dict[str, Any]) -> list[dict[str, Any]]:
    return [q for q in day["quests"] if q["state"] == "offered"]


async def all_events(database: Database) -> list[Event]:
    async with database.sessionmaker() as session:
        return list(await session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


async def test_today_before_checkin(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await onboarded(client)

    response = await client.get("/days/today", headers=user.headers)

    assert response.status_code == 200
    assert_matches(response, "getToday")
    day = response.json()
    assert day["pool_status"] == "none" and day["checkin"] is None and day["quests"] == []
    assert day["limits"] == {"taken": 0, "max_taken": 3, "replacements_left": 5}


async def test_checkin_with_llm_builds_ranked_pool(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = ScriptedLLM()
    use_tools(app, [llm], forecast())
    user = await onboarded(client)

    day = await checkin(client, user, SECRET_LINE, "tired")

    assert day["pool_status"] == "ready"
    assert day["checkin"]["text"] == SECRET_LINE and day["checkin"]["mood"] == "tired"
    assert day["weather"] == {"temperature_c": 12.0, "condition": "clear"}
    sources = [q["source"] for q in day["quests"]]
    assert sources == ["checkin_task"] + ["catalog"] * 5
    assert day["quests"][1]["category"] == "rest"
    assert day["quests"][1]["why"] == "Подходит тебе сегодня"
    assert all(q["base_points"] > 0 for q in day["quests"])
    # The prompt holds no name, Telegram id or city.
    assert "Саша" not in "".join(llm.prompts) and "Калининград" not in "".join(llm.prompts)

    recorded = await all_events(database)
    assert [e.type for e in recorded] == ["checkin_submitted", "pool_shown"]
    assert recorded[0].payload["parsed_by"] == "llm" and recorded[0].payload["mood"] == "tired"
    shown = recorded[1].payload
    assert shown["provider"] == "fake" and shown["ranked_by"] == "llm"
    assert len(shown["shown_ids"]) == 5 and set(shown["shown_ids"]) <= set(shown["candidate_ids"])
    assert SECRET_LINE not in json.dumps([e.payload for e in recorded], ensure_ascii=False)


async def test_checkin_without_llm_uses_code_and_weather(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    use_tools(app, [], forecast(temp=8, code=63))  # rain all day
    user = await onboarded(client)

    day = await checkin(client, user, "позвонить маме\nпочитать книгу", "tired")

    assert day["pool_status"] == "ready"
    tasks = [q for q in day["quests"] if q["source"] == "checkin_task"]
    assert [(t["title"], t["category"]) for t in tasks] == [
        ("позвонить маме", "social"),
        ("почитать книгу", "learning"),
    ]
    catalog = [q for q in day["quests"] if q["source"] == "catalog"]
    assert len(catalog) == 6
    assert catalog[0]["category"] == "rest"
    assert not [q for q in catalog if q["outdoor"] and q["duration_min"] >= 30]
    shown = (await all_events(database))[1].payload
    assert shown["provider"] == "code" and shown["weather"] == "rain"


async def test_take_limit_and_states(app: FastAPI, client: httpx.AsyncClient) -> None:
    use_tools(app, [], forecast())
    user = await onboarded(client)
    other = await onboarded(client, 2002)
    quests = offered(await checkin(client, user))

    taken = []
    for quest in quests[:3]:
        response = await client.post(f"/day-quests/{quest['id']}/take", headers=user.headers)
        assert response.status_code == 200
        assert_matches(response, "takeQuest")
        taken.append(response.json())
    assert {q["state"] for q in taken} == {"taken"}

    fourth = await client.post(f"/day-quests/{quests[3]['id']}/take", headers=user.headers)
    again = await client.post(f"/day-quests/{quests[0]['id']}/take", headers=user.headers)
    foreign = await client.post(f"/day-quests/{quests[4]['id']}/take", headers=other.headers)

    assert fourth.status_code == 409 and fourth.json()["type"].endswith("/daily-limit-reached")
    assert again.status_code == 409 and again.json()["type"].endswith("/quest-not-offered")
    assert foreign.status_code == 404
    day = (await client.get("/days/today", headers=user.headers)).json()
    assert day["limits"]["taken"] == 3


async def test_replace_until_limit(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    use_tools(app, [], forecast())
    user = await onboarded(client)
    day = await checkin(client, user)
    first = offered(day)[0]

    response = await client.post(
        f"/day-quests/{first['id']}/replace", json={"reason": "no_time"}, headers=user.headers
    )

    assert response.status_code == 200, response.text
    assert_matches(response, "replaceQuest")
    body = response.json()
    assert body["replaced"]["state"] == "replaced" and body["replacements_left"] == 4
    replacement = body["replacement"]
    assert replacement is not None
    assert (replacement["category"], replacement["duration_min"]) != (
        first["category"],
        first["duration_min"],
    )
    day = (await client.get("/days/today", headers=user.headers)).json()
    ids = [q["id"] for q in day["quests"]]
    assert first["id"] not in ids and replacement["id"] in ids

    current = replacement
    for _ in range(4):
        response = await client.post(f"/day-quests/{current['id']}/replace", headers=user.headers)
        assert response.status_code == 200
        current = response.json()["replacement"] or offered(day)[1]
    over = await client.post(f"/day-quests/{current['id']}/replace", headers=user.headers)
    assert over.status_code == 409 and over.json()["type"].endswith("/no-replacements-left")

    rejected = [e for e in await all_events(database) if e.type == "quest_rejected"]
    assert len(rejected) == 5 and rejected[0].payload["reason"] == "no_time"

    # A replaced quest does not come back with a new check-in the same day.
    replaced_templates = {e.payload["template_id"] for e in rejected}
    day = await checkin(client, user, "", "normal")
    assert day["limits"]["replacements_left"] == 0
    shown = [e for e in await all_events(database) if e.type == "pool_shown"][-1].payload
    assert not replaced_templates & set(shown["candidate_ids"])


async def test_repeat_checkin_keeps_taken_quests(app: FastAPI, client: httpx.AsyncClient) -> None:
    use_tools(app, [], forecast())
    user = await onboarded(client)
    first = offered(await checkin(client, user, "", "normal"))
    await client.post(f"/day-quests/{first[0]['id']}/take", headers=user.headers)

    day = await checkin(client, user, "сходить в зал", "energetic")

    assert day["checkin"]["mood"] == "energetic"
    states = {q["id"]: q["state"] for q in day["quests"]}
    assert states[first[0]["id"]] == "taken"
    assert not {q["id"] for q in first[1:]} & set(states)
    assert day["quests"][0]["id"] == first[0]["id"]


async def test_own_quest_is_taken_and_counts(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await onboarded(client)

    response = await client.post(
        "/day-quests",
        json={"title": "  Дописать главу  ", "category": "project", "duration_min": 45},
        headers=user.headers,
    )

    assert response.status_code == 201
    assert_matches(response, "addOwnQuest")
    quest = response.json()
    assert quest["title"] == "Дописать главу" and quest["state"] == "taken"
    assert quest["source"] == "custom" and quest["base_points"] == 35
    for _ in range(2):
        await client.post(
            "/day-quests",
            json={"title": "Ещё", "category": "home", "duration_min": 10},
            headers=user.headers,
        )
    over = await client.post(
        "/day-quests",
        json={"title": "Четвёртый", "category": "home", "duration_min": 10},
        headers=user.headers,
    )
    assert over.status_code == 409
    day = (await client.get("/days/today", headers=user.headers)).json()
    assert day["pool_status"] == "none" and day["limits"]["taken"] == 3


async def test_checkin_validation(client: httpx.AsyncClient) -> None:
    user = await onboarded(client)
    too_long = await client.put(
        "/days/today/checkin", json={"text": "я" * 1001, "mood": "normal"}, headers=user.headers
    )
    bad_mood = await client.put("/days/today/checkin", json={"mood": "sad"}, headers=user.headers)
    assert too_long.status_code == 422 and bad_mood.status_code == 422
    assert "я" * 50 not in too_long.text
