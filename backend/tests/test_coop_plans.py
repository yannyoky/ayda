import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from ayda.app import coop as coop_app
from ayda.app import notifications
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import auth, quests
from ayda.modules.analytics.models import Event
from ayda.modules.quests.models import PointsEntry
from tests.conftest import FakeRealtime
from tests.contract import assert_matches
from tests.helpers import SignedIn, sign_in
from tests.test_completion import complete, own_quest
from tests.test_coop import answer, today_quests, trio
from tests.test_feed import befriend

SHOPPING = ["Паста", "Помидоры", "Сыр"]


def cooking(owner: SignedIn, shopper: SignedIn, friend: SignedIn) -> dict[str, Any]:
    return {
        "title": "Ужин из пасты",
        "category": "home",
        "duration_min": 30,
        "friend_ids": [shopper.user_id],
        "parts": [
            {"title": "Купить продукты", "assignee_id": shopper.user_id, "items": SHOPPING},
            {
                "title": "Приготовить пасту",
                "assignee_id": owner.user_id,
                "opens_after": 0,
                "place": {"name": "Моя кухня"},
            },
        ],
    }


async def plan(client: httpx.AsyncClient, owner: SignedIn, body: dict[str, Any]) -> httpx.Response:
    return await client.post("/coops", json=body, headers=owner.headers)


async def get(client: httpx.AsyncClient, user: SignedIn, coop_id: str) -> dict[str, Any]:
    response = await client.get(f"/coops/{coop_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    assert_matches(response, "getCoop")
    return response.json()


def handoff_url(coop_id: str, part_id: str, tail: str = "") -> str:
    return f"/coops/{coop_id}/parts/{part_id}/handoff{tail}"


async def test_cooking_plan_from_shopping_to_the_shared_bonus(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob, eve = await trio(client)
    created = await plan(client, alice, cooking(alice, bob, eve))
    assert created.status_code == 201, created.text
    assert_matches(created, "createPlan")
    coop = created.json()
    shop, cook = coop["parts"]
    assert coop["kind"] == "parts" and coop["my_quest_id"] is None
    assert [(p["state"], p["assignee"]["first_name"]) for p in coop["parts"]] == [
        ("open", "Боря"),
        ("locked", "Алиса"),
    ]
    assert cook["opens_after"] == shop["id"] and cook["place"] == {
        "name": "Моя кухня",
        "address": None,
        "lat": None,
        "lon": None,
        "link": None,
        "source": None,
        "source_id": None,
        "price_hint": None,
    }
    assert [i["text"] for i in shop["items"]] == SHOPPING
    assert realtime.sent[-1][1] == {"type": "coop.updated", "coop_id": coop["id"]}
    # Nobody has a quest yet: the first part waits for Bob to accept, the second is locked.
    assert [q["source"] for q in await today_quests(client, alice)] == []

    # Bob's quest for the part is outside the daily limit of three.
    for _ in range(3):
        await own_quest(client, bob)
    joined = await answer(client, bob, coop["id"], "accept")
    assert joined.status_code == 200, joined.text
    assert_matches(joined, "acceptCoop")
    [shop_quest] = [q for q in await today_quests(client, bob) if q["title"] == "Купить продукты"]
    assert shop_quest["state"] == "taken" and shop_quest["coop_id"] == coop["id"]
    assert joined.json()["parts"][0]["my_quest_id"] == shop_quest["id"]
    assert joined.json()["conversation_id"] is not None

    # Only the assignee ticks the list, and everyone sees it live.
    item_url = f"/coops/{coop['id']}/parts/{shop['id']}/items/{shop['items'][0]['id']}"
    foreign = await client.patch(item_url, json={"done": True}, headers=alice.headers)
    assert foreign.status_code == 403
    assert_matches(foreign, "setCoopItem")
    locked_url = f"/coops/{coop['id']}/parts/{cook['id']}/items/{uuid.uuid4()}"
    assert (
        await client.patch(locked_url, json={"done": True}, headers=alice.headers)
    ).status_code == 404
    ticked = await client.patch(item_url, json={"done": True}, headers=bob.headers)
    assert ticked.status_code == 200
    assert_matches(ticked, "setCoopItem")
    assert [i["done"] for i in ticked.json()["parts"][0]["items"]] == [True, False, False]
    assert realtime.sent[-1] == (
        {alice.user_id, bob.user_id},
        {"type": "coop.updated", "coop_id": coop["id"]},
    )
    again = await client.patch(item_url, json={"done": False}, headers=bob.headers)
    assert again.json()["parts"][0]["items"][0]["done"] is False

    # Completing the first part opens the second for Alice.
    first = await complete(client, bob, shop_quest["id"], visibility="personal")
    assert first.status_code == 200, first.text
    assert first.json()["coop_bonus"] == 0
    [cook_quest] = [
        q for q in await today_quests(client, alice) if q["title"] == "Приготовить пасту"
    ]
    assert cook_quest["state"] == "taken" and cook_quest["coop_id"] == coop["id"]
    middle = await get(client, alice, coop["id"])
    assert [p["state"] for p in middle["parts"]] == ["done", "open"]
    assert middle["parts"][1]["my_quest_id"] == cook_quest["id"]
    assert middle["bonus_awarded"] is False
    assert [p["completed"] for p in middle["participants"]] == [False, True]

    # Completing the last one gives each who did a part one bonus.
    last = await complete(client, alice, cook_quest["id"], visibility="personal")
    body = last.json()
    assert body["points_awarded"] == 10 and body["coop_bonus"] == 5
    final = await get(client, bob, coop["id"])
    assert final["bonus_awarded"] is True
    assert [p["completed"] for p in final["participants"]] == [True, True]
    async with database.sessionmaker() as session:
        rows = list(
            await session.scalars(select(PointsEntry).where(PointsEntry.kind == "coop_bonus"))
        )
        assert sorted((str(r.user_id), r.points) for r in rows) == sorted(
            [(alice.user_id, 5), (bob.user_id, 5)]
        )
        events = list(await session.scalars(select(Event.type).where(Event.type.like("coop_%"))))
        assert sorted(events) == [
            "coop_answered",
            "coop_bonus",
            "coop_bonus",
            "coop_created",
            "coop_part_completed",
            "coop_part_completed",
            "coop_part_opened",
            "coop_part_opened",
        ]
        [created_event] = list(
            await session.scalars(select(Event).where(Event.type == "coop_created"))
        )
        assert created_event.payload["kind"] == "parts" and created_event.payload["parts"] == 2
        # Free text of a plan never reaches the events.
        assert "Купить" not in str([e.payload for e in await session.scalars(select(Event))])


async def test_handing_a_part_to_a_friend(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database, settings: Settings
) -> None:
    alice, bob, eve = await trio(client)
    await befriend(client, bob, eve)
    coop = (await plan(client, alice, cooking(alice, bob, eve))).json()
    shop, _ = coop["parts"]
    await answer(client, bob, coop["id"], "accept")
    [bob_quest] = [q for q in await today_quests(client, bob) if q["title"] == "Купить продукты"]

    url = handoff_url(coop["id"], shop["id"])
    assert (
        await client.post(url, json={"friend_id": eve.user_id}, headers=alice.headers)
    ).status_code == 403
    stranger = await sign_in(client, 4004, "Гоша")
    assert (
        await client.post(url, json={"friend_id": stranger.user_id}, headers=bob.headers)
    ).status_code == 403
    assert (
        await client.post(url, json={"friend_id": bob.user_id}, headers=bob.headers)
    ).status_code == 422

    offered = await client.post(url, json={"friend_id": eve.user_id}, headers=bob.headers)
    assert offered.status_code == 200, offered.text
    assert_matches(offered, "offerHandoff")
    assert offered.json()["parts"][0]["handoff"]["for_me"] is False
    assert realtime.sent[-1][0] == {alice.user_id, bob.user_id, eve.user_id}
    twice = await client.post(url, json={"friend_id": alice.user_id}, headers=bob.headers)
    assert twice.status_code == 409
    assert_matches(twice, "offerHandoff")

    # Eve is not in the plan yet but can see the offer, and gets a bot notice.
    seen = await get(client, eve, coop["id"])
    assert seen["my_status"] == "invited" and seen["conversation_id"] is None
    assert seen["parts"][0]["handoff"]["for_me"] is True
    async with database.sessionmaker() as session:
        [job] = list(
            await session.scalars(select(Job).where(Job.payload["kind"].astext == "coop.handoff"))
        )
        assert job.payload["user_id"] == eve.user_id
        coop_app.register(settings)
        me = await auth.get_user(session, uuid.UUID(eve.user_id))
        assert me is not None
        notice = await notifications.RENDERERS["coop.handoff"](session, me, job.payload["params"])
        assert notice is not None
        assert notice.text == (
            "Боря просит тебя взять часть «Купить продукты» в плане «Ужин из пасты» 🤝"
        )

    # Declining changes nothing; so does withdrawing.
    declined = await client.post(url + "/decline", headers=eve.headers)
    assert declined.status_code == 200
    assert_matches(declined, "declineHandoff")
    assert declined.json()["my_status"] == "declined"
    assert (await get(client, bob, coop["id"]))["parts"][0]["handoff"] is None
    assert (await client.post(url + "/decline", headers=eve.headers)).status_code == 404
    await client.post(url, json={"friend_id": eve.user_id}, headers=bob.headers)
    withdrawn = await client.delete(url, headers=bob.headers)
    assert withdrawn.status_code == 200
    assert_matches(withdrawn, "withdrawHandoff")
    assert withdrawn.json()["parts"][0]["handoff"] is None
    assert (await client.delete(url, headers=bob.headers)).status_code == 404
    assert (await client.post(url + "/accept", headers=eve.headers)).status_code == 404

    # Accepting moves the part and its quest.
    await client.post(url, json={"friend_id": eve.user_id}, headers=bob.headers)
    for _ in range(3):
        await own_quest(client, eve)
    taken = await client.post(url + "/accept", headers=eve.headers)
    assert taken.status_code == 200, taken.text
    assert_matches(taken, "acceptHandoff")
    part = taken.json()["parts"][0]
    assert part["assignee"]["first_name"] == "Ева" and part["handoff"] is None
    assert taken.json()["my_status"] == "accepted" and taken.json()["conversation_id"]
    [eve_quest] = [q for q in await today_quests(client, eve) if q["title"] == "Купить продукты"]
    assert part["my_quest_id"] == eve_quest["id"] and eve_quest["id"] != bob_quest["id"]
    assert all(q["id"] != bob_quest["id"] for q in await today_quests(client, bob))
    chat = await client.get(
        f"/conversations/{taken.json()['conversation_id']}", headers=eve.headers
    )
    assert chat.status_code == 200

    # The new assignee completes it; the old one cannot.
    assert (await complete(client, bob, bob_quest["id"], visibility="personal")).status_code == 409
    assert (await complete(client, eve, eve_quest["id"], visibility="personal")).status_code == 200
    done = await client.post(url, json={"friend_id": alice.user_id}, headers=eve.headers)
    assert done.status_code == 409
    async with database.sessionmaker() as session:
        answers = list(
            await session.scalars(
                select(Event.payload["answer"].astext).where(Event.type == "coop_handoff_answered")
            )
        )
        assert sorted(answers) == ["accepted", "declined"]


async def test_handing_a_locked_part_and_the_size_of_a_plan(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob, eve = await trio(client)
    coop = (await plan(client, alice, cooking(alice, bob, eve))).json()
    _, cook = coop["parts"]
    url = handoff_url(coop["id"], cook["id"])
    await client.post(url, json={"friend_id": eve.user_id}, headers=alice.headers)
    taken = await client.post(url + "/accept", headers=eve.headers)
    assert taken.status_code == 200
    assert taken.json()["parts"][1]["my_quest_id"] is None  # still locked: no quest yet
    assert [q["source"] for q in await today_quests(client, eve)] == []

    # When the part before it is done, the quest goes to its new assignee.
    await answer(client, bob, coop["id"], "accept")
    [shop_quest] = [q for q in await today_quests(client, bob) if q["title"] == "Купить продукты"]
    await complete(client, bob, shop_quest["id"], visibility="personal")
    [mine] = await today_quests(client, eve)
    assert mine["title"] == "Приготовить пасту"

    # A plan holds the owner and three friends.
    extra = [await sign_in(client, 5000 + i, f"Друг{i}") for i in range(2)]
    await befriend(client, bob, eve)
    for friend in extra:
        await befriend(client, alice, friend)
        await befriend(client, bob, friend)
    body = cooking(alice, bob, eve) | {"friend_ids": [bob.user_id, eve.user_id, extra[0].user_id]}
    full_plan = (await plan(client, alice, body)).json()
    for friend in (bob, eve, extra[0]):
        await answer(client, friend, full_plan["id"], "accept")
    shop_part = full_plan["parts"][0]["id"]
    offer = await client.post(
        handoff_url(full_plan["id"], shop_part),
        json={"friend_id": extra[1].user_id},
        headers=bob.headers,
    )
    assert offer.status_code == 200, offer.text
    full = await client.post(
        handoff_url(full_plan["id"], shop_part, "/accept"), headers=extra[1].headers
    )
    assert full.status_code == 409
    assert_matches(full, "acceptHandoff")
    assert full.json()["type"].endswith("/coop-full")
    # A participant can still take a part over when the plan is full.
    await client.delete(handoff_url(full_plan["id"], shop_part), headers=bob.headers)
    await client.post(
        handoff_url(full_plan["id"], shop_part),
        json={"friend_id": eve.user_id},
        headers=bob.headers,
    )
    ok = await client.post(handoff_url(full_plan["id"], shop_part, "/accept"), headers=eve.headers)
    assert ok.status_code == 200


@pytest.mark.usefixtures("take_guard_of_3")
async def test_same_plan_with_a_place_and_time(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob, _ = await trio(client)
    # Now, not later: a plan lives until the day ends at 04:00, so any time ahead fails when
    # the suite runs just before that.
    starts = datetime.now(UTC).replace(microsecond=0)
    body = {
        "title": "Кофе в центре",
        "category": "social",
        "duration_min": 60,
        "friend_ids": [bob.user_id],
        "starts_at": starts.isoformat(),
        "place": {
            "name": "Кофейня на углу",
            "address": "ул. Ленина, 1",
            "lat": 54.7,
            "lon": 20.5,
            "link": "https://www.openstreetmap.org/node/1",
            "source": "osm",
            "source_id": "node/1",
        },
    }
    created = await plan(client, alice, body)
    assert created.status_code == 201, created.text
    assert_matches(created, "createPlan")
    coop = created.json()
    assert coop["kind"] == "same" and coop["parts"] is None
    assert coop["place"]["name"] == "Кофейня на углу"
    assert datetime.fromisoformat(coop["starts_at"]) == starts
    [mine] = [q for q in await today_quests(client, alice) if q["id"] == coop["my_quest_id"]]
    assert mine["state"] == "taken" and mine["source"] == "coop"
    joined = await answer(client, bob, coop["id"], "accept")
    assert joined.json()["place"]["address"] == "ул. Ленина, 1"
    await complete(client, alice, mine["id"], visibility="personal")
    last = await complete(client, bob, joined.json()["my_quest_id"], visibility="personal")
    assert last.json()["coop_bonus"] > 0

    # An own quest of the owner counts toward the daily limit, as for a co-op from a quest.
    for _ in range(2):
        await own_quest(client, alice)
    limited = await plan(client, alice, body)
    assert limited.status_code == 409
    assert_matches(limited, "createPlan")
    assert limited.json()["type"].endswith("/daily-limit-reached")


async def test_plan_rules(client: httpx.AsyncClient, realtime: FakeRealtime) -> None:
    alice, bob, eve = await trio(client)
    stranger = await sign_in(client, 4004, "Гоша")
    base = cooking(alice, bob, eve)

    def with_parts(*parts: dict[str, Any]) -> dict[str, Any]:
        return base | {"parts": list(parts)}

    shop = {"title": "Купить", "assignee_id": bob.user_id}
    cook = {"title": "Готовить", "assignee_id": alice.user_id}
    failures = {
        "not a friend": base | {"friend_ids": [stranger.user_id]},
        "one part": with_parts(shop),
        "six parts": with_parts(*[shop] * 6),
        "assignee outside the plan": with_parts(shop, cook | {"assignee_id": eve.user_id}),
        "waits for itself": with_parts(shop | {"opens_after": 0}, cook),
        "waits for a later part": with_parts(shop | {"opens_after": 1}, cook),
        "nothing opens": with_parts(shop | {"opens_after": 1}, cook | {"opens_after": 0}),
        "too many items": with_parts(shop | {"items": ["x"] * 21}, cook),
        "after the day": base | {"starts_at": (datetime.now(UTC) + timedelta(days=3)).isoformat()},
        "part after the day": with_parts(
            shop | {"starts_at": (datetime.now(UTC) + timedelta(days=3)).isoformat()}, cook
        ),
        "insecure link": base | {"place": {"name": "x", "link": "http://example.com"}},
    }
    for name, body in failures.items():
        response = await plan(client, alice, body)
        assert response.status_code in (403, 422), (name, response.text)
        assert_matches(response, "createPlan")
    assert (await client.get("/coops", headers=alice.headers)).json()["items"] == []


async def test_declining_gives_the_parts_back_to_the_owner(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob, eve = await trio(client)
    coop = (await plan(client, alice, cooking(alice, bob, eve))).json()
    declined = await answer(client, bob, coop["id"], "decline")
    assert declined.status_code == 200
    seen = await get(client, alice, coop["id"])
    assert [p["assignee"]["first_name"] for p in seen["parts"]] == ["Алиса", "Алиса"]
    # The open part is now Alice's: she has its quest.
    [quest] = await today_quests(client, alice)
    assert quest["title"] == "Купить продукты"
    assert seen["parts"][0]["my_quest_id"] == quest["id"]


async def test_erasing_an_assignee_returns_the_part_to_the_owner(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob, eve = await trio(client)
    await befriend(client, bob, eve)
    coop = (await plan(client, alice, cooking(alice, bob, eve))).json()
    await answer(client, bob, coop["id"], "accept")
    url = handoff_url(coop["id"], coop["parts"][0]["id"])
    await client.post(url, json={"friend_id": eve.user_id}, headers=bob.headers)
    async with database.sessionmaker() as session:
        await quests.erase_user(session, uuid.UUID(bob.user_id))
        await session.commit()
    seen = await get(client, alice, coop["id"])
    assert seen["parts"][0]["assignee"]["first_name"] == "Алиса"
    assert seen["parts"][0]["handoff"] is None
