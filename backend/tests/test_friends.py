from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import update

from ayda.core.db import Database
from ayda.modules import social
from tests.contract import assert_matches
from tests.helpers import sign_in


async def test_invite_link_makes_mutual_friends(client: httpx.AsyncClient) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")

    created = await client.post("/invites", headers=alice.headers)
    assert created.status_code == 201
    assert_matches(created, "createInvite")
    invite = created.json()
    assert invite["url"] == f"https://t.me/ayda_quest_bot?startapp={invite['code']}"
    again = (await client.post("/invites", headers=alice.headers)).json()
    assert again["code"] == invite["code"]  # reused while fresh

    accepted = await client.post(f"/invites/{invite['code']}/accept", headers=bob.headers)
    assert accepted.status_code == 200
    assert_matches(accepted, "acceptInvite")
    assert accepted.json()["first_name"] == "Алиса"
    repeat = await client.post(f"/invites/{invite['code']}/accept", headers=bob.headers)
    assert repeat.status_code == 200 and repeat.json()["since"] == accepted.json()["since"]

    for user, name in ((alice, "Боря"), (bob, "Алиса")):
        listed = await client.get("/friends", headers=user.headers)
        assert_matches(listed, "listFriends")
        assert [f["first_name"] for f in listed.json()["items"]] == [name]


async def test_invite_errors(client: httpx.AsyncClient, database: Database) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    code = (await client.post("/invites", headers=alice.headers)).json()["code"]

    own = await client.post(f"/invites/{code}/accept", headers=alice.headers)
    unknown = await client.post("/invites/nosuchcode123/accept", headers=bob.headers)
    short = await client.post("/invites/abc/accept", headers=bob.headers)
    async with database.sessionmaker() as session:
        await session.execute(
            update(social.Invite).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    expired = await client.post(f"/invites/{code}/accept", headers=bob.headers)

    assert own.status_code == 409
    assert unknown.status_code == 404
    assert short.status_code == 422
    assert expired.status_code == 410
    fresh = (await client.post("/invites", headers=alice.headers)).json()["code"]
    assert fresh != code


async def test_remove_friend(client: httpx.AsyncClient) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    code = (await client.post("/invites", headers=alice.headers)).json()["code"]
    await client.post(f"/invites/{code}/accept", headers=bob.headers)

    removed = await client.delete(f"/friends/{bob.user_id}", headers=alice.headers)
    again = await client.delete(f"/friends/{bob.user_id}", headers=alice.headers)

    assert removed.status_code == 204 and again.status_code == 404
    assert (await client.get("/friends", headers=bob.headers)).json()["items"] == []
