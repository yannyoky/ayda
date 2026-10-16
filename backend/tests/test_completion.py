import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import select, text, update

from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import quests, social
from ayda.modules.analytics.models import Event
from tests.contract import assert_matches
from tests.helpers import SignedIn
from tests.test_day import forecast, onboarded, use_tools


async def own_quest(client: httpx.AsyncClient, user: SignedIn, duration: int = 30) -> str:
    response = await client.post(
        "/day-quests",
        json={"title": "Дописать главу", "category": "project", "duration_min": duration},
        headers=user.headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def complete(
    client: httpx.AsyncClient, user: SignedIn, quest_id: str, **body: object
) -> httpx.Response:
    return await client.post(f"/day-quests/{quest_id}/complete", json=body, headers=user.headers)


async def add_media(database: Database, user: SignedIn, status: str = "pending") -> str:
    media_id = uuid.uuid4()
    async with database.sessionmaker() as session:
        session.add(
            social.Media(
                id=media_id,
                owner_id=uuid.UUID(user.user_id),
                storage_key=f"uploads/{media_id}",
                content_type="image/jpeg",
                size_bytes=1000,
                status=status,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    return str(media_id)


async def test_personal_completion_awards_points_without_post(
    client: httpx.AsyncClient, database: Database
) -> None:
    user = await onboarded(client)
    quest_id = await own_quest(client, user, duration=30)

    response = await complete(client, user, quest_id, visibility="personal")

    assert response.status_code == 200, response.text
    assert_matches(response, "completeQuest")
    body = response.json()
    assert body["points_awarded"] == 10  # 20 x 0.5
    assert body["points_breakdown"] == {
        "base": 20,
        "visibility_multiplier": 0.5,
        "streak_multiplier": 1.0,
    }
    assert body["post_id"] is None
    assert body["streak"]["current_days"] == 1
    assert body["quest"]["state"] == "completed" and body["quest"]["visibility"] == "personal"

    day = (await client.get("/days/today", headers=user.headers)).json()
    assert day["points_today"] == day["points_week"] == 10
    assert day["streak"]["current_days"] == 1
    assert day["quests"][0]["points_awarded"] == 10

    again = await complete(client, user, quest_id, visibility="personal")
    assert again.status_code == 409 and again.json()["type"].endswith("/quest-already-completed")
    async with database.sessionmaker() as session:
        types = list(await session.scalars(select(Event.type).order_by(Event.id)))
        assert await session.scalar(select(social.Post)) is None
    assert types == ["quest_taken", "quest_completed"]


async def test_routine_post_hides_details(client: httpx.AsyncClient, database: Database) -> None:
    user = await onboarded(client)
    quest_id = await own_quest(client, user, duration=60)

    body = (await complete(client, user, quest_id, visibility="routine")).json()

    assert body["points_awarded"] == 26  # 35 x 0.75 = 26.25
    async with database.sessionmaker() as session:
        post = (await session.scalars(select(social.Post))).one()
    assert str(post.id) == body["post_id"]
    assert (post.kind, post.quest_title, post.caption, post.category) == (
        "routine",
        None,
        None,
        "project",
    )


async def test_friends_proof_needs_photos_and_starts_cleaning(
    client: httpx.AsyncClient, database: Database
) -> None:
    user = await onboarded(client)
    other = await onboarded(client, 2002)
    quest_id = await own_quest(client, user)

    no_photo = await complete(client, user, quest_id, visibility="friends")
    with_caption_personal = await complete(
        client, user, quest_id, visibility="personal", caption="ура"
    )
    foreign = await complete(
        client, user, quest_id, visibility="friends", media_ids=[await add_media(database, other)]
    )
    assert no_photo.status_code == 422 and no_photo.json()["type"].endswith("/photo-required")
    assert with_caption_personal.status_code == 422
    assert foreign.status_code == 422 and foreign.json()["type"].endswith("/invalid-media")

    pending = await add_media(database, user, "pending")
    ready = await add_media(database, user, "ready")
    response = await complete(
        client,
        user,
        quest_id,
        visibility="friends",
        caption=" Готово! ",
        media_ids=[pending, ready],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["points_awarded"] == 20
    async with database.sessionmaker() as session:
        post = (await session.scalars(select(social.Post))).one()
        media = {str(m.id): m for m in await session.scalars(select(social.Media))}
        jobs = list(await session.scalars(select(Job)))
        events = list(await session.scalars(select(Event).order_by(Event.id)))
    assert (post.kind, post.quest_title, post.caption) == ("proof", "Дописать главу", "Готово!")
    assert media[pending].post_id == post.id and media[pending].status == "processing"
    assert media[ready].post_id == post.id and media[ready].status == "ready"
    assert [(j.kind, j.payload) for j in jobs] == [("media.process", {"media_id": pending})]
    proof = next(e for e in events if e.type == "proof_posted")
    assert proof.payload["kind"] == "proof" and proof.payload["photos"] == 2

    # A used photo can't be attached again.
    second = await own_quest(client, user)
    reused = await complete(client, user, second, visibility="friends", media_ids=[ready])
    assert reused.status_code == 422


async def test_only_taken_unexpired_quests_complete(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    use_tools(app, [], forecast())
    user = await onboarded(client)
    day = (
        await client.put("/days/today/checkin", json={"mood": "normal"}, headers=user.headers)
    ).json()
    offered_id = day["quests"][0]["id"]

    not_taken = await complete(client, user, offered_id, visibility="personal")
    missing = await complete(client, user, str(uuid.uuid4()), visibility="personal")
    assert not_taken.status_code == 409 and not_taken.json()["type"].endswith("/quest-not-taken")
    assert missing.status_code == 404

    quest_id = await own_quest(client, user)
    async with database.sessionmaker() as session:
        await session.execute(
            update(quests.DayQuest)
            .where(quests.DayQuest.id == uuid.UUID(quest_id))
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    expired = await complete(client, user, quest_id, visibility="personal")
    assert expired.status_code == 409 and expired.json()["type"].endswith("/quest-expired")


async def test_streak_bonus_applies_from_day_seven(
    client: httpx.AsyncClient, database: Database
) -> None:
    user = await onboarded(client)
    today = (await client.get("/days/today", headers=user.headers)).json()["local_date"]
    async with database.sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO quests.streaks (user_id, current_days, best_days, last_counted_date)"
                " VALUES (:u, 6, 6, :d)"
            ),
            {"u": uuid.UUID(user.user_id), "d": date.fromisoformat(today) - timedelta(days=1)},
        )
        await session.commit()
    quest_id = await own_quest(client, user, duration=60)

    body = (await complete(client, user, quest_id, visibility="routine")).json()

    assert body["streak"]["current_days"] == 7
    assert body["points_breakdown"]["streak_multiplier"] == 1.1
    assert body["points_awarded"] == 29  # 35 x 0.75 x 1.1 = 28.875


async def test_ledger_is_append_only(client: httpx.AsyncClient, database: Database) -> None:
    user = await onboarded(client)
    quest_id = await own_quest(client, user)
    await complete(client, user, quest_id, visibility="personal")

    async with database.sessionmaker() as session:
        try:
            await session.execute(text("UPDATE quests.points_ledger SET points = 1000"))
        except Exception as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError("ledger update was allowed")
