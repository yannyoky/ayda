import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

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
from tests.test_feed import befriend


async def trio(client: httpx.AsyncClient) -> tuple[SignedIn, SignedIn, SignedIn]:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    eve = await sign_in(client, 3003, "Ева")
    await befriend(client, alice, bob)
    await befriend(client, alice, eve)
    return alice, bob, eve


async def create(
    client: httpx.AsyncClient, owner: SignedIn, quest_id: str, *friends: SignedIn
) -> httpx.Response:
    return await client.post(
        f"/day-quests/{quest_id}/coop",
        json={"friend_ids": [f.user_id for f in friends]},
        headers=owner.headers,
    )


async def answer(
    client: httpx.AsyncClient, user: SignedIn, coop_id: str, action: str
) -> httpx.Response:
    return await client.post(f"/coops/{coop_id}/{action}", headers=user.headers)


async def today_quests(client: httpx.AsyncClient, user: SignedIn) -> list[dict[str, Any]]:
    return (await client.get("/days/today", headers=user.headers)).json()["quests"]


async def test_coop_quest_with_shared_chat_and_bonus(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob, eve = await trio(client)
    quest_id = await own_quest(client, alice)

    created = await create(client, alice, quest_id, bob, eve)
    assert created.status_code == 201, created.text
    assert_matches(created, "createCoop")
    coop = created.json()
    assert coop["my_status"] == "owner" and coop["my_quest_id"] == quest_id
    assert [(p["user"]["first_name"], p["status"]) for p in coop["participants"]] == [
        ("Алиса", "owner"),
        ("Боря", "invited"),
        ("Ева", "invited"),
    ]
    assert realtime.sent[-1] == (
        {alice.user_id, bob.user_id, eve.user_id},
        {"type": "coop.updated", "coop_id": coop["id"]},
    )

    invites = await client.get("/coops", headers=bob.headers)
    assert_matches(invites, "listCoops")
    [invite] = invites.json()["items"]
    assert invite["my_status"] == "invited"
    assert invite["my_quest_id"] is None and invite["conversation_id"] is None

    joined = await answer(client, bob, coop["id"], "accept")
    assert joined.status_code == 200
    assert_matches(joined, "acceptCoop")
    bob_quest = joined.json()["my_quest_id"]
    [mine] = [q for q in await today_quests(client, bob) if q["id"] == bob_quest]
    assert mine["source"] == "coop" and mine["state"] == "taken"
    assert mine["coop_id"] == coop["id"] and mine["title"] == "Дописать главу"
    declined = await answer(client, eve, coop["id"], "decline")
    assert declined.status_code == 200
    assert_matches(declined, "declineCoop")
    assert (await client.get("/coops", headers=eve.headers)).json()["items"] == []

    # The shared chat is named after the quest and has those who joined.
    conversation_id = joined.json()["conversation_id"]
    chat = (await client.get(f"/conversations/{conversation_id}", headers=bob.headers)).json()
    assert chat["kind"] == "coop" and chat["title"] == "Дописать главу"
    assert [m["first_name"] for m in chat["members"]] == ["Алиса"]
    assert (
        await client.get(f"/conversations/{conversation_id}", headers=eve.headers)
    ).status_code == 404

    first = await complete(client, alice, quest_id, visibility="personal")
    assert first.status_code == 200
    assert first.json()["coop_bonus"] == 0 and first.json()["quest"]["coop_id"] == coop["id"]
    last = await complete(client, bob, bob_quest, visibility="personal")
    assert_matches(last, "completeQuest")
    body = last.json()
    assert body["points_awarded"] == 10 and body["coop_bonus"] == 5
    assert body["quest"]["points_awarded"] == 15

    # The owner got the bonus too: in their day, their week and a bot notice.
    [owner_quest] = [q for q in await today_quests(client, alice) if q["id"] == quest_id]
    assert owner_quest["points_awarded"] == 15
    day = (await client.get("/days/today", headers=alice.headers)).json()
    assert day["points_today"] == 15
    got = await client.get(f"/coops/{coop['id']}", headers=alice.headers)
    assert_matches(got, "getCoop")
    assert got.json()["bonus_awarded"] is True
    assert [p["completed"] for p in got.json()["participants"]] == [True, True, False]
    async with database.sessionmaker() as session:
        bonus_jobs = list(
            await session.scalars(select(Job).where(Job.payload["kind"].astext == "coop.bonus"))
        )
        assert [j.payload["user_id"] for j in bonus_jobs] == [alice.user_id]
        rows = list(
            await session.scalars(select(PointsEntry).where(PointsEntry.kind == "coop_bonus"))
        )
        assert sorted(r.points for r in rows) == [5, 5]
        events = list(await session.scalars(select(Event.type).where(Event.type.like("coop_%"))))
        assert sorted(events) == [
            "coop_answered",
            "coop_answered",
            "coop_bonus",
            "coop_bonus",
            "coop_created",
        ]


@pytest.mark.usefixtures("take_guard_of_3")
async def test_coop_rules(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob, eve = await trio(client)
    stranger = await sign_in(client, 4004, "Гоша")
    quest_id = await own_quest(client, alice)

    not_friend = await create(client, alice, quest_id, stranger)
    assert not_friend.status_code == 403
    assert_matches(not_friend, "createCoop")
    twice = await client.post(
        f"/day-quests/{quest_id}/coop",
        json={"friend_ids": [bob.user_id, bob.user_id]},
        headers=alice.headers,
    )
    assert twice.status_code == 422
    foreign = await create(client, bob, quest_id, alice)
    assert foreign.status_code == 404

    coop = (await create(client, alice, quest_id, bob, eve)).json()
    again = await create(client, alice, quest_id, bob)
    assert again.status_code == 409
    assert_matches(again, "createCoop")
    assert again.json()["type"].endswith("/quest-already-coop")
    assert (await client.get(f"/coops/{coop['id']}", headers=stranger.headers)).status_code == 404

    # A joined co-op quest cannot become a co-op of its own.
    bob_quest = (await answer(client, bob, coop["id"], "accept")).json()["my_quest_id"]
    assert (await create(client, bob, bob_quest, alice)).status_code == 409
    repeated = await answer(client, bob, coop["id"], "accept")
    assert repeated.status_code == 409
    assert_matches(repeated, "acceptCoop")
    assert (await answer(client, bob, coop["id"], "decline")).status_code == 409

    # A completed quest cannot be shared.
    done = await own_quest(client, alice)
    await complete(client, alice, done, visibility="personal")
    assert (await create(client, alice, done, bob)).status_code == 409

    # Accepting counts toward the daily limit of taken quests.
    full = await own_quest(client, alice)
    second = (await create(client, alice, full, eve)).json()
    for _ in range(3):
        await own_quest(client, eve)
    limited = await answer(client, eve, second["id"], "accept")
    assert limited.status_code == 409
    assert limited.json()["type"].endswith("/daily-limit-reached")

    # After the owner's day the invitation is over.
    async with database.sessionmaker() as session:
        await session.execute(
            update(quests.Coop)
            .where(quests.Coop.id == uuid.UUID(coop["id"]))
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    over = await answer(client, eve, coop["id"], "accept")
    assert over.status_code == 410
    assert_matches(over, "acceptCoop")


async def test_declining_the_last_invitation_brings_no_bonus_alone(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob, _ = await trio(client)
    quest_id = await own_quest(client, alice)
    coop = (await create(client, alice, quest_id, bob)).json()
    await complete(client, alice, quest_id, visibility="personal")
    await answer(client, bob, coop["id"], "decline")
    got = (await client.get(f"/coops/{coop['id']}", headers=alice.headers)).json()
    assert got["bonus_awarded"] is False
    [quest] = [q for q in await today_quests(client, alice) if q["id"] == quest_id]
    assert quest["points_awarded"] == 10


async def test_invite_notice(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database, settings: Settings
) -> None:
    alice, bob, _ = await trio(client)
    coop = (await create(client, alice, await own_quest(client, alice), bob)).json()
    coop_app.register(settings)
    render = notifications.RENDERERS[coop_app.INVITE_KIND]
    async with database.sessionmaker() as session:
        [job] = list(
            await session.scalars(select(Job).where(Job.payload["kind"].astext == "coop.invite"))
        )
        assert job.payload["user_id"] == bob.user_id
        me = await auth.get_user(session, uuid.UUID(bob.user_id))
        assert me is not None
        notice = await render(session, me, job.payload["params"])
        assert notice is not None
        assert notice.text.startswith("Алиса зовёт тебя на совместный квест «Дописать главу»")
        assert notice.button is not None
        assert notice.button.url.endswith(f"startapp=q{uuid.UUID(coop['id']).hex}")

    await answer(client, bob, coop["id"], "accept")
    async with database.sessionmaker() as session:
        me = await auth.get_user(session, uuid.UUID(bob.user_id))
        assert me is not None
        assert await render(session, me, {"coop_id": coop["id"]}) is None


async def test_erasing_the_owner_removes_the_coop(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob, _ = await trio(client)
    coop = (await create(client, alice, await own_quest(client, alice), bob)).json()
    await answer(client, bob, coop["id"], "accept")
    async with database.sessionmaker() as session:
        await quests.erase_user(session, uuid.UUID(alice.user_id))
        await session.commit()
    assert (await client.get(f"/coops/{coop['id']}", headers=bob.headers)).status_code == 404
    # Bob keeps his quest of the day.
    assert [q["source"] for q in await today_quests(client, bob)] == ["coop"]
    assert (await today_quests(client, bob))[0]["coop_id"] is None
