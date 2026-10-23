"""Local events (US-19): the nightly load and event quests in the daily pool."""

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from ayda.app import events as local_events
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import auth, events
from ayda.modules.analytics.models import Event
from ayda.modules.events import CityRef, Listing, ListingData
from tests.contract import assert_matches
from tests.helpers import sign_in
from tests.test_day import TZ, checkin, forecast, offered, onboarded, use_tools

KALININGRAD = 435
SOVETSK = 438  # same region (39)
MOSCOW = 1069
SVETLOGORSK = 456
PRIMORSK = 455  # the smallest town of the region

TODAY = datetime.now(ZoneInfo(TZ)).date()
NOW = datetime.combine(TODAY, time(10, 0), ZoneInfo(TZ)).astimezone(UTC)


def listing(
    source_id: str,
    starts_in: timedelta,
    city_id: int = KALININGRAD,
    region: str = "39",
    *,
    title: str | None = None,
    free: bool = False,
    hours: float | None = 2,
    source: str = "timepad",
) -> ListingData:
    starts = NOW + starts_in
    return ListingData(
        source=source,
        source_id=source_id,
        title=title or f"Событие {source_id}",
        starts_at=starts,
        ends_at=starts + timedelta(hours=hours) if hours else None,
        venue="Дом искусств",
        address="ул. Театральная, 1",
        lat=None,
        lon=None,
        city_id=city_id,
        region_code=region,
        is_free=free,
        price_min=None if free else 500,
        url=f"https://org.timepad.ru/event/{source_id}/",
        category="city",
    )


async def seed(database: Database, items: list[ListingData], now: datetime = NOW) -> None:
    async with database.sessionmaker() as session:
        await events.save_listings(session, items, now)
        await session.commit()


async def listing_ids(database: Database) -> dict[str, int]:
    async with database.sessionmaker() as session:
        rows = await session.execute(select(Listing.source_id, Listing.id))
        return {r[0]: r[1] for r in rows}


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr("ayda.api.days._now", lambda: NOW)
    return NOW


SEEDED = [
    listing("free", timedelta(hours=3), free=True, title="Лекция о море"),
    listing("paid", timedelta(hours=5), title="Концерт"),
    listing("same-title", timedelta(hours=6), title="концерт"),
    listing("soon", timedelta(minutes=30)),
    listing("past", timedelta(hours=-2)),
    listing("long", timedelta(hours=4), hours=6, title="Фестиваль на весь день"),
    listing("region", timedelta(hours=4), city_id=SOVETSK, title="Ярмарка"),
    listing("moscow", timedelta(hours=3), city_id=MOSCOW, region="77"),
    listing("tomorrow", timedelta(days=1)),
]
ALLOWED = {"free", "paid", "long", "region"}


async def test_event_quests_join_the_pool(
    app: FastAPI, client: httpx.AsyncClient, database: Database, fixed_now: datetime
) -> None:
    use_tools(app, [], forecast())
    await seed(database, SEEDED)
    ids = await listing_ids(database)
    user = await onboarded(client)

    day = await checkin(client, user)

    quests = offered(day)
    assert len(quests) == 6
    event_quests = [q for q in quests if q["source"] == "event"]
    assert len(event_quests) == 2
    assert [q["source"] for q in quests[:2]] == ["catalog", "catalog"]
    by_id = {v: k for k, v in ids.items()}
    shown = {q["event"]["url"].rsplit("/", 2)[-2] for q in event_quests}
    assert shown <= ALLOWED
    for quest in event_quests:
        info = quest["event"]
        assert info["source"] == "timepad" and info["venue"] == "Дом искусств"
        assert datetime.fromisoformat(info["starts_at"]) >= NOW + timedelta(hours=1)
        assert quest["duration_min"] in (120, 240)
        if info["city"] is not None:
            assert info["city"] == "Советск" and quest["why"] == "Стоит съездить: Советск."
    assert all(q["event"] is None for q in quests if q["source"] != "event")

    async with database.sessionmaker() as session:
        shown_event = await session.scalar(select(Event).where(Event.type == "pool_shown"))
    assert shown_event is not None and shown_event.schema_version == 2
    payload = shown_event.payload
    assert len(payload["event_ids"]) == 2
    assert {by_id[i] for i in payload["event_candidate_ids"]} == ALLOWED


async def test_the_check_in_brings_the_event_that_fits_it_first(
    app: FastAPI, client: httpx.AsyncClient, database: Database, fixed_now: datetime
) -> None:
    use_tools(app, [], forecast())
    await seed(
        database,
        [
            listing("fair", timedelta(hours=3), title="Ярмарка мёда"),
            listing("sea", timedelta(hours=4), title="Лекция о море"),
            listing("jazz", timedelta(hours=4), city_id=SOVETSK, title="Джазовый вечер"),
        ],
    )
    user = await onboarded(client)

    day = await checkin(client, user, "Хочется послушать джаз")

    event_quests = [q for q in offered(day) if q["source"] == "event"]
    assert event_quests[0]["title"] == "Джазовый вечер"
    assert len(event_quests) == 2


async def test_no_events_for_a_user_without_listings_nearby(
    app: FastAPI, client: httpx.AsyncClient, database: Database, fixed_now: datetime
) -> None:
    use_tools(app, [], forecast())
    await seed(database, [listing("moscow", timedelta(hours=3), city_id=MOSCOW, region="77")])
    user = await onboarded(client)

    day = await checkin(client, user)

    assert [q["source"] for q in offered(day)] == ["catalog"] * 6


async def test_short_free_time_skips_long_events(
    client: httpx.AsyncClient, database: Database
) -> None:
    """Busy all day: quests are at most 60 minutes, and events take at least that."""
    await seed(database, [listing("short", timedelta(hours=3), hours=1), SEEDED[1]])
    user = await onboarded(client)

    async with database.sessionmaker() as session:
        found = await auth.get_user(session, uuid.UUID(user.user_id))
        assert found is not None
        options = await local_events.event_candidates(
            session, found, NOW + timedelta(hours=18), 60, set(), NOW
        )
    assert [o.event["url"].rsplit("/", 2)[-2] for o in options if o.event] == ["short"]


async def test_replacing_an_event_offers_another_event_then_a_catalog_quest(
    app: FastAPI, client: httpx.AsyncClient, database: Database, fixed_now: datetime
) -> None:
    use_tools(app, [], forecast())
    await seed(database, SEEDED[:3])  # two allowed events, one repeated title
    user = await onboarded(client)
    day = await checkin(client, user)
    event_quests = [q for q in offered(day) if q["source"] == "event"]
    assert len(event_quests) == 2
    # Replace one: the other is already in the pool, so a catalog quest comes instead.
    response = await client.post(
        f"/day-quests/{event_quests[0]['id']}/replace",
        json={"reason": "dont_want"},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text
    assert_matches(response, "replaceQuest")
    assert response.json()["replacement"]["source"] == "catalog"


async def test_replacing_an_event_brings_the_next_event(
    app: FastAPI, client: httpx.AsyncClient, database: Database, fixed_now: datetime
) -> None:
    use_tools(app, [], forecast())
    await seed(database, [s for s in SEEDED if s.source_id in ALLOWED])
    user = await onboarded(client)
    day = await checkin(client, user)
    in_pool = {q["event"]["url"] for q in offered(day) if q["event"]}
    first = next(q for q in offered(day) if q["source"] == "event")

    response = await client.post(
        f"/day-quests/{first['id']}/replace", json={"reason": "no_time"}, headers=user.headers
    )

    assert response.status_code == 200, response.text
    replacement = response.json()["replacement"]
    assert replacement["source"] == "event"
    assert replacement["event"]["url"] not in in_pool

    # A new check-in does not bring the replaced event back.
    day = await checkin(client, user, mood="energetic")
    urls = {q["event"]["url"] for q in offered(day) if q["event"]}
    assert first["event"]["url"] not in urls


async def test_event_quest_can_be_taken_and_completed(
    app: FastAPI, client: httpx.AsyncClient, database: Database, fixed_now: datetime
) -> None:
    use_tools(app, [], forecast())
    await seed(database, SEEDED[:2])
    user = await onboarded(client)
    day = await checkin(client, user)
    quest = next(q for q in offered(day) if q["source"] == "event")

    taken = await client.post(f"/day-quests/{quest['id']}/take", headers=user.headers)
    assert taken.status_code == 200, taken.text
    assert_matches(taken, "takeQuest")
    done = await client.post(
        f"/day-quests/{quest['id']}/complete",
        json={"visibility": "personal"},
        headers=user.headers,
    )
    assert done.status_code == 200, done.text
    assert_matches(done, "completeQuest")
    assert done.json()["quest"]["event"]["title"] == quest["event"]["title"]

    today = await client.get("/days/today", headers=user.headers)
    assert_matches(today, "getToday")
    async with database.sessionmaker() as session:
        recorded = await session.scalar(select(Event).where(Event.type == "quest_completed"))
    assert recorded is not None and recorded.payload["event_id"] is not None


# --- the nightly load ----------------------------------------------------------------------


class FakeSource:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.cities: list[str] = []

    def supports(self, city: CityRef) -> bool:
        return True

    async def fetch(self, city: CityRef, since: datetime, until: datetime) -> list[ListingData]:
        self.cities.append(city.name)
        if self.fail:
            raise httpx.ConnectError("down")
        assert until - since == timedelta(days=7)
        return [listing(f"{city.id}-1", timedelta(hours=3), city.id, city.region_code)]


async def test_ingest_loads_user_cities_and_region_centers(
    client: httpx.AsyncClient, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ayda.modules.events.listings.REGION_TOWNS", 1)
    await onboarded(client)  # Kaliningrad
    other = await sign_in(client, 2002)
    await client.patch("/me/profile", json={"city_id": SOVETSK}, headers=other.headers)
    good, broken = FakeSource("timepad"), FakeSource("kudago", fail=True)
    await seed(database, [listing("old", timedelta(days=-5))])

    async with database.sessionmaker() as session:
        saved = await local_events.run_ingest(session, [broken, good], NOW)
        await session.commit()
    async with database.sessionmaker() as session:
        again = await local_events.run_ingest(session, [good], NOW)
        await session.commit()

    assert saved == {"kudago": 0, "timepad": 2} and again == {"timepad": 2}
    assert sorted(good.cities) == ["Калининград", "Калининград", "Советск", "Советск"]
    assert sorted(broken.cities) == ["Калининград", "Советск"]
    assert set(await listing_ids(database)) == {f"{KALININGRAD}-1", f"{SOVETSK}-1"}


async def test_the_biggest_towns_of_the_region_are_loaded(database: Database) -> None:
    async with database.sessionmaker() as session:
        cities = await events.cities_to_load(session, [SOVETSK, PRIMORSK])
    names = [c.name for c in cities]
    # 15 biggest towns of the Kaliningrad region plus the users' own small town.
    assert len(names) == 16 and {"Калининград", "Советск", "Светлогорск", "Приморск"} <= set(names)
    assert {c.region_code for c in cities} == {"39"}


async def test_ingest_is_scheduled_once_a_day_after_its_time(
    settings: Settings, database: Database
) -> None:
    moscow = ZoneInfo("Europe/Moscow")
    early = datetime(2026, 10, 17, 3, 0, tzinfo=moscow)
    late = datetime(2026, 10, 17, 4, 5, tzinfo=moscow)
    async with database.sessionmaker() as session:
        assert not await local_events.schedule_ingest(session, settings, early)
        assert await local_events.schedule_ingest(session, settings, late)
        assert not await local_events.schedule_ingest(session, settings, late + timedelta(hours=1))
        off = settings.model_copy(update={"events_sources": ""})
        assert not await local_events.schedule_ingest(session, off, late + timedelta(days=1))
        await session.commit()
        count = await session.scalar(
            select(func.count()).select_from(Job).where(Job.kind == local_events.INGEST_JOB)
        )
    assert count == 1


def test_default_sources_follow_settings(settings: Settings) -> None:
    http = httpx.AsyncClient()
    names = [s.name for s in local_events.default_sources(settings, http)]
    assert names == ["timepad", "kudago"]
    only = settings.model_copy(update={"events_sources": "kudago, unknown"})
    assert [s.name for s in local_events.default_sources(only, http)] == ["kudago"]
