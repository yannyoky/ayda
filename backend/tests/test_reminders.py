import uuid
from datetime import UTC, datetime, time, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import select, update

from ayda.app import notifications, reminders
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import auth
from ayda.modules.analytics.models import Event
from ayda.modules.quests.days import local_day
from ayda.worker import build_worker
from tests.helpers import SignedIn, make_init_data, sign_in
from tests.test_bot import FakeSender
from tests.test_day import forecast, use_tools
from tests.test_feed import befriend, post

KALININGRAD = "Europe/Kaliningrad"  # UTC+2
VLADIVOSTOK = "Asia/Vladivostok"  # UTC+10


async def configure(
    database: Database,
    user: SignedIn,
    tz: str = KALININGRAD,
    morning: time | None = time(8, 30),
    evening: time | None = time(21, 0),
) -> None:
    async with database.sessionmaker() as session:
        await session.execute(
            update(auth.User)
            .where(auth.User.id == uuid.UUID(user.user_id))
            .values(
                timezone=tz,
                morning_reminder_at=morning,
                evening_reminder_at=evening,
                onboarded_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def queued(database: Database) -> list[tuple[str, str]]:
    async with database.sessionmaker() as session:
        jobs = await session.scalars(select(Job).order_by(Job.id))
        return [(j.payload["kind"], j.payload["user_id"]) for j in jobs]


async def schedule(database: Database, now: datetime) -> int:
    async with database.sessionmaker() as session:
        count = await reminders.schedule_reminders(session, now)
        await session.commit()
    return count


async def test_reminders_follow_each_users_time_zone(
    client: httpx.AsyncClient, database: Database
) -> None:
    kld = await sign_in(client, 1001, "Калининград")
    vvo = await sign_in(client, 2002, "Владивосток")
    off = await sign_in(client, 3003, "Без напоминаний")
    await configure(database, kld)
    await configure(database, vvo, VLADIVOSTOK, morning=time(16, 30))
    await configure(database, off, morning=None, evening=None)

    at = datetime(2026, 10, 16, 6, 30, tzinfo=UTC)  # 08:30 KLD, 16:30 VVO
    assert await schedule(database, at - timedelta(minutes=1)) == 0
    assert await schedule(database, at) == 2
    assert await schedule(database, at + timedelta(minutes=4)) == 0  # deduplicated
    assert await schedule(database, at + timedelta(minutes=5)) == 0  # window passed
    assert sorted(await queued(database)) == sorted(
        [(reminders.MORNING, kld.user_id), (reminders.MORNING, vvo.user_id)]
    )

    evening = datetime(2026, 10, 16, 19, 2, tzinfo=UTC)  # 21:02 KLD
    assert await schedule(database, evening) == 1


async def test_morning_reminder_is_skipped_after_checkin(
    app: FastAPI, client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    use_tools(app, [], forecast())
    user = await sign_in(client)
    await configure(database, user)
    reminders.register(settings)
    day = local_day(datetime.now(UTC), KALININGRAD).isoformat()
    render = notifications.RENDERERS[reminders.MORNING]

    async with database.sessionmaker() as session:
        me = await auth.get_user(session, uuid.UUID(user.user_id))
        assert me is not None
        before = await render(session, me, {"day": day})
    await client.put("/days/today/checkin", json={"mood": "normal"}, headers=user.headers)
    async with database.sessionmaker() as session:
        me = await auth.get_user(session, uuid.UUID(user.user_id))
        assert me is not None
        after = await render(session, me, {"day": day})

    assert before is not None and before.button is not None
    assert before.button.url.endswith("startapp=r-morning")
    assert after is None


async def test_evening_reminder_lists_open_quests(
    app: FastAPI, client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    use_tools(app, [], forecast())
    user = await sign_in(client)
    await configure(database, user)
    reminders.register(settings)
    day = local_day(datetime.now(UTC), KALININGRAD).isoformat()
    render = notifications.RENDERERS[reminders.EVENING]

    async def rendered() -> notifications.Message | None:
        async with database.sessionmaker() as session:
            me = await auth.get_user(session, uuid.UUID(user.user_id))
            assert me is not None
            return await render(session, me, {"day": day})

    assert await rendered() is None  # no check-in
    await client.put("/days/today/checkin", json={"mood": "normal"}, headers=user.headers)
    assert await rendered() is None  # nothing taken
    quest = (
        await client.post(
            "/day-quests",
            json={"title": "Дочитать книгу", "category": "learning", "duration_min": 30},
            headers=user.headers,
        )
    ).json()
    message = await rendered()
    assert message is not None and "• Дочитать книгу" in message.text
    assert "выполнено 0" in message.text

    await client.post(
        f"/day-quests/{quest['id']}/complete", json={"visibility": "personal"}, headers=user.headers
    )
    assert await rendered() is None  # every taken quest is closed


async def test_sent_and_opened_events(
    client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    user = await sign_in(client)
    await configure(database, user)
    await schedule(database, datetime(2026, 10, 16, 6, 31, tzinfo=UTC))
    sender = FakeSender()

    assert await build_worker(settings, database, sender=sender).run_one()
    reopened = await client.post(
        "/auth/telegram", json={"init_data": make_init_data(start_param="r-morning")}
    )

    assert len(sender.sent) == 1 and reopened.status_code == 200
    async with database.sessionmaker() as session:
        events = [(e.type, e.payload) for e in await session.scalars(select(Event))]
    assert ("reminder_sent", {"kind": reminders.MORNING}) in events
    assert ("reminder_opened", {"kind": "morning"}) in events


async def test_hourly_digest_of_reactions(
    client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    await befriend(client, alice, bob)
    post_id = await post(client, database, alice, "friends")
    await client.put(f"/posts/{post_id}/like", headers=bob.headers)
    await client.put(f"/posts/{post_id}/like", headers=alice.headers)  # own like: not counted
    await client.post(f"/posts/{post_id}/comments", json={"text": "Огонь"}, headers=bob.headers)
    reminders.register(settings)

    next_hour = datetime.now(UTC) + timedelta(hours=1)
    async with database.sessionmaker() as session:
        assert await reminders.schedule_digests(session, next_hour) == 1
        assert await reminders.schedule_digests(session, next_hour) == 0
        assert await reminders.schedule_digests(session, datetime.now(UTC)) == 0
        await session.commit()
    sender = FakeSender()
    assert await build_worker(settings, database, sender=sender).run_one()

    [(chat_id, message)] = sender.sent
    assert chat_id == 1001
    assert message.text == "Друзья отметили твои посты, лайков: 1, комментариев: 1."


async def test_sunday_summary(
    client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    user = await sign_in(client)
    await configure(database, user)
    sunday_evening = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)  # 20:00 in Kaliningrad

    async with database.sessionmaker() as session:
        assert await reminders.schedule_weekly(session, sunday_evening - timedelta(days=1)) == 0
        assert await reminders.schedule_weekly(session, sunday_evening) == 1
        assert await reminders.schedule_weekly(session, sunday_evening) == 0
        await session.commit()
    assert await queued(database) == [(reminders.WEEKLY, user.user_id)]
