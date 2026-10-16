import uuid
from datetime import date, timedelta

import httpx
from sqlalchemy import text

from ayda.core.db import Database
from tests.contract import assert_matches
from tests.helpers import SignedIn, sign_in
from tests.test_feed import befriend, post


async def set_streak(database: Database, user: SignedIn, days: int) -> None:
    async with database.sessionmaker() as session:
        await session.execute(
            text("UPDATE quests.streaks SET current_days = :d, best_days = :d WHERE user_id = :u"),
            {"d": days, "u": uuid.UUID(user.user_id)},
        )
        await session.commit()


async def test_ladder_ranks_friends_by_weekly_points(
    client: httpx.AsyncClient, database: Database
) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    carol = await sign_in(client, 3003, "Катя")
    stranger = await sign_in(client, 4004, "Чужой")
    await befriend(client, alice, bob)
    await befriend(client, alice, carol)
    await post(client, database, alice, "personal")  # 10 points, details hidden
    await post(client, database, bob, "friends")  # 20
    await post(client, database, carol, "routine")  # 15
    await post(client, database, stranger, "friends")

    response = await client.get("/ladder", headers=alice.headers)

    assert response.status_code == 200
    assert_matches(response, "getLadder")
    ladder = response.json()
    rows = [
        (e["rank"], e["user"]["first_name"], e["points"], e["is_me"]) for e in ladder["entries"]
    ]
    assert rows == [(1, "Боря", 20, False), (2, "Катя", 15, False), (3, "Алиса", 10, True)]
    assert date.fromisoformat(ladder["week_start"]).weekday() == 0
    assert all(e["streak_days"] == 1 for e in ladder["entries"])

    previous = (await client.get("/ladder?week=previous", headers=alice.headers)).json()
    assert [e["points"] for e in previous["entries"]] == [0, 0, 0]
    assert date.fromisoformat(previous["week_start"]) == date.fromisoformat(
        ladder["week_start"]
    ) - timedelta(days=7)


async def test_ties_go_to_longer_streak(client: httpx.AsyncClient, database: Database) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    await befriend(client, alice, bob)
    await post(client, database, alice, "routine")
    await post(client, database, bob, "routine")
    await set_streak(database, bob, 5)

    entries = (await client.get("/ladder", headers=alice.headers)).json()["entries"]

    assert [e["user"]["first_name"] for e in entries] == ["Боря", "Алиса"]
    assert entries[0]["streak_days"] == 5
