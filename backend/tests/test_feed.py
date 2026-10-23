import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select

from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import social
from ayda.modules.analytics.models import Event
from ayda.modules.quests.models import PointsEntry
from tests.contract import assert_matches
from tests.helpers import SignedIn, sign_in


async def befriend(client: httpx.AsyncClient, a: SignedIn, b: SignedIn) -> None:
    code = (await client.post("/invites", headers=a.headers)).json()["code"]
    assert (await client.post(f"/invites/{code}/accept", headers=b.headers)).status_code == 200


async def ready_photo(database: Database, owner: SignedIn) -> str:
    media_id = uuid.uuid4()
    async with database.sessionmaker() as session:
        session.add(
            social.Media(
                id=media_id,
                owner_id=uuid.UUID(owner.user_id),
                storage_key=f"photos/{media_id}.jpg",
                content_type="image/jpeg",
                size_bytes=1000,
                width=1600,
                height=1200,
                status="ready",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    return str(media_id)


async def post(
    client: httpx.AsyncClient,
    database: Database,
    user: SignedIn,
    visibility: str,
    title: str = "Пробежка у моря",
    photo: bool = True,
) -> str | None:
    quest = await client.post(
        "/day-quests",
        json={"title": title, "category": "sport", "duration_min": 30},
        headers=user.headers,
    )
    body: dict[str, object] = {"visibility": visibility}
    if visibility == "friends":
        body["caption"] = "Было холодно"
        if photo:
            body["media_ids"] = [await ready_photo(database, user)]
    done = await client.post(
        f"/day-quests/{quest.json()['id']}/complete", json=body, headers=user.headers
    )
    assert done.status_code == 200, done.text
    return done.json()["post_id"]


async def test_feed_shows_friends_posts_only(client: httpx.AsyncClient, database: Database) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    carol = await sign_in(client, 3003, "Катя")
    await befriend(client, alice, bob)
    proof = await post(client, database, alice, "friends")
    text_only = await post(client, database, alice, "friends", "Только текст", photo=False)
    assert await post(client, database, alice, "personal") is None

    page = await client.get("/feed", headers=bob.headers)

    assert page.status_code == 200
    assert_matches(page, "getFeed")
    items = page.json()["items"]
    assert [p["id"] for p in items] == [text_only, proof]
    assert items[0]["kind"] == "proof" and items[0]["quest_title"] == "Только текст"
    assert items[0]["photos"] == [] and items[0]["caption"] == "Было холодно"
    assert items[1]["quest_title"] == "Пробежка у моря" and items[1]["caption"] == "Было холодно"
    assert items[1]["author"]["first_name"] == "Алиса"
    [photo] = items[1]["photos"]
    assert photo["width"] == 1600 and "X-Amz-Signature" in photo["url"]

    assert (await client.get("/feed", headers=carol.headers)).json()["items"] == []
    own = (await client.get("/feed", headers=alice.headers)).json()["items"]
    assert len(own) == 2


async def test_feed_pagination(client: httpx.AsyncClient, database: Database) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    ids = [await post(client, database, alice, "friends", photo=False) for _ in range(3)]

    first = (await client.get("/feed?limit=2", headers=alice.headers)).json()
    second = (
        await client.get(f"/feed?limit=2&cursor={first['next_cursor']}", headers=alice.headers)
    ).json()
    bad = await client.get("/feed?cursor=garbage", headers=alice.headers)

    assert [p["id"] for p in first["items"] + second["items"]] == ids[::-1]
    assert second["next_cursor"] is None
    assert bad.status_code == 422


async def test_likes_and_comments(client: httpx.AsyncClient, database: Database) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    carol = await sign_in(client, 3003, "Катя")
    await befriend(client, alice, bob)
    post_id = await post(client, database, alice, "friends")

    liked = await client.put(f"/posts/{post_id}/like", headers=bob.headers)
    again = await client.put(f"/posts/{post_id}/like", headers=bob.headers)
    stranger = await client.put(f"/posts/{post_id}/like", headers=carol.headers)
    assert_matches(liked, "likePost")
    assert again.json() == {"like_count": 1, "liked_by_me": True}
    assert stranger.status_code == 404

    comment = await client.post(
        f"/posts/{post_id}/comments", json={"text": "  Красава!  "}, headers=bob.headers
    )
    assert comment.status_code == 201
    assert_matches(comment, "addComment")
    assert comment.json()["text"] == "Красава!" and comment.json()["can_delete"]
    too_long = await client.post(
        f"/posts/{post_id}/comments", json={"text": "я" * 501}, headers=bob.headers
    )
    assert too_long.status_code == 422

    listed = await client.get(f"/posts/{post_id}/comments", headers=alice.headers)
    assert_matches(listed, "listComments")
    [item] = listed.json()["items"]
    assert item["author"]["first_name"] == "Боря" and item["can_delete"]  # post author

    feed = (await client.get("/feed", headers=alice.headers)).json()["items"][0]
    assert (feed["like_count"], feed["liked_by_me"], feed["comment_count"]) == (1, False, 1)

    assert (
        await client.delete(f"/comments/{item['id']}", headers=carol.headers)
    ).status_code == 404
    assert (
        await client.delete(f"/comments/{item['id']}", headers=alice.headers)
    ).status_code == 204
    assert (await client.get(f"/posts/{post_id}/comments", headers=bob.headers)).json()[
        "items"
    ] == []

    unliked = await client.delete(f"/posts/{post_id}/like", headers=bob.headers)
    assert unliked.json() == {"like_count": 0, "liked_by_me": False}

    async with database.sessionmaker() as session:
        reactions = list(await session.scalars(select(Event).where(Event.type == "reaction_added")))
    assert sorted(e.payload["reaction"] for e in reactions) == ["comment", "like"]
    assert all("Красава" not in str(e.payload) for e in reactions)


async def test_removed_friend_loses_access_at_once(
    client: httpx.AsyncClient, database: Database
) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    await befriend(client, alice, bob)
    post_id = await post(client, database, alice, "friends")

    await client.delete(f"/friends/{bob.user_id}", headers=alice.headers)

    assert (await client.get("/feed", headers=bob.headers)).json()["items"] == []
    assert (await client.put(f"/posts/{post_id}/like", headers=bob.headers)).status_code == 404
    assert (await client.get(f"/posts/{post_id}/comments", headers=bob.headers)).status_code == 404


async def test_delete_post_removes_photos_keeps_points(
    client: httpx.AsyncClient, database: Database
) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    await befriend(client, alice, bob)
    post_id = await post(client, database, alice, "friends")

    forbidden = await client.delete(f"/posts/{post_id}", headers=bob.headers)
    deleted = await client.delete(f"/posts/{post_id}", headers=alice.headers)
    again = await client.delete(f"/posts/{post_id}", headers=alice.headers)

    assert forbidden.status_code == 403 and deleted.status_code == 204 and again.status_code == 404
    assert (await client.get("/feed", headers=bob.headers)).json()["items"] == []
    async with database.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(social.Media)) == 0
        [job] = list(await session.scalars(select(Job).where(Job.kind == "media.delete_files")))
        stored = await session.get(social.Post, uuid.UUID(post_id))
        points = await session.scalar(select(func.sum(PointsEntry.points)))
    assert any(k.startswith("photos/") for k in job.payload["keys"])
    assert stored is not None and stored.caption is None and stored.quest_title is None
    assert points == 20
