"""OpenStreetMap venues for meetups (ADR 0011): loading, snapshots and candidates."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from ayda.api.schemas import Place
from ayda.app import events as local_events
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.modules import events
from ayda.modules.events import OverpassSource, Venue, VenueLoad

KALININGRAD = 435
NOW = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
NOON = datetime(2026, 10, 24, 12, 0)  # a Saturday, local time


def node(
    id: int, name: str | None = "Кофейня", amenity: str = "cafe", **tags: str
) -> dict[str, Any]:
    all_tags = {"amenity": amenity} | ({"name": name} if name else {}) | tags
    return {"type": "node", "id": id, "lat": 54.71, "lon": 20.51, "tags": all_tags}


PAYLOAD = {
    "elements": [
        node(1, "Кофейня на углу", **{"addr:street": "Ленина", "addr:housenumber": "1"}),
        node(2, "Закрытая", opening_hours="Mo-Fr 09:00-18:00"),
        node(3, "Ночной бар", "bar", opening_hours="Mo-Su 18:00-02:00"),
        node(4, None),  # no name
        node(5, "Парковка", "parking"),
        {
            "type": "way",
            "id": 6,
            "center": {"lat": 54.72, "lon": 20.52},
            "tags": {
                "amenity": "restaurant",
                "name": "  Ресторан   у моря ",
                "website": "http://insecure.example",
                "cuisine": "seafood",
            },
        },
        {"type": "node", "id": 7, "tags": {"amenity": "cafe", "name": "Без координат"}},
    ]
}


class Overpass:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    def source(self, *urls: str) -> OverpassSource:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self))
        return OverpassSource(client, urls or ("https://overpass.test/api",))


def ok(payload: dict[str, Any] = PAYLOAD) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_parse_keeps_named_venues_of_the_five_kinds_with_coordinates() -> None:
    parsed = {v.osm_id: v for v in events.parse_venues(PAYLOAD)}
    assert sorted(parsed) == [1, 2, 3, 6]
    assert parsed[1].address == "Ленина, 1" and parsed[1].kind == "cafe"
    assert parsed[6].name == "Ресторан у моря" and (parsed[6].lat, parsed[6].lon) == (54.72, 20.52)
    assert parsed[6].website is None and parsed[6].cuisine == "seafood"


async def test_a_city_is_queried_with_its_center_and_a_user_agent_free_body() -> None:
    overpass = Overpass(ok())
    items = await overpass.source().fetch(54.71, 20.51, 7000)
    assert len(items) == 4
    [request] = overpass.requests
    body = request.content.decode()
    assert "around%3A7000%2C54.71000%2C20.51000" in body
    assert "amenity" in body and "restaurant%7Ccafe%7Cbar%7Cpub%7Cfast_food" in body


async def test_the_next_instance_is_tried_and_all_failing_raises() -> None:
    overpass = Overpass(httpx.Response(429), ok())
    source = overpass.source("https://one.test/api", "https://two.test/api")
    assert len(await source.fetch(54.7, 20.5, 5000)) == 4
    assert [r.url.host for r in overpass.requests] == ["one.test", "two.test"]
    failing = Overpass(httpx.Response(504))
    with pytest.raises(httpx.HTTPError):
        await failing.source("https://one.test/api", "https://two.test/api").fetch(54.7, 20.5, 1)
    with pytest.raises(ValueError):
        await Overpass(httpx.Response(200, text="<html>")).source().fetch(54.7, 20.5, 1)


async def test_monthly_load_replaces_the_snapshot_and_keeps_it_when_a_load_fails(
    database: Database,
) -> None:
    source = Overpass(ok()).source()
    async with database.sessionmaker() as session:
        assert await events.load_venues(session, source, [KALININGRAD], 7000, NOW) == {
            KALININGRAD: 4
        }
        await session.commit()
        # Loaded a day ago: not due again.
        assert (
            await events.load_venues(session, source, [KALININGRAD], 7000, NOW + timedelta(days=1))
            == {}
        )

        # A month later one venue is gone and one is new.
        later = NOW + timedelta(days=31)
        payload = {"elements": [node(1, "Кофейня на углу"), node(8, "Новая пекарня")]}
        fresh = Overpass(ok(payload)).source()
        assert await events.load_venues(session, fresh, [KALININGRAD], 7000, later) == {
            KALININGRAD: 2
        }
        ids = set(await session.scalars(select(Venue.osm_id)))
        assert ids == {1, 8}

        # A failing load changes nothing and is tried again on the next run.
        broken = Overpass(httpx.Response(504)).source()
        much_later = later + timedelta(days=31)
        assert await events.load_venues(session, broken, [KALININGRAD], 7000, much_later) == {}
        assert set(await session.scalars(select(Venue.osm_id))) == {1, 8}
        load = await session.get(VenueLoad, KALININGRAD)
        assert load is not None and load.loaded_at == later and load.venues == 2


async def test_an_empty_city_is_not_queried_every_night(database: Database) -> None:
    overpass = Overpass(ok({"elements": []}))
    async with database.sessionmaker() as session:
        await events.load_venues(session, overpass.source(), [KALININGRAD], 7000, NOW)
        await events.load_venues(
            session, overpass.source(), [KALININGRAD], 7000, NOW + timedelta(days=2)
        )
        await session.commit()
    assert len(overpass.requests) == 1


async def test_a_few_cities_per_run(database: Database) -> None:
    overpass = Overpass(ok({"elements": []}))
    async with database.sessionmaker() as session:
        done = await events.load_venues(
            session, overpass.source(), [435, 438, 1069], 7000, NOW, limit=2
        )
        assert len(done) == 2
        rest = await events.load_venues(
            session, overpass.source(), [435, 438, 1069], 7000, NOW, limit=2
        )
        assert len(rest) == 1 and set(done).isdisjoint(rest)


async def test_candidates_are_open_first_then_with_an_address_then_close(
    database: Database,
) -> None:
    async with database.sessionmaker() as session:
        await events.load_venues(session, Overpass(ok()).source(), [KALININGRAD], 7000, NOW)
        # Saturday noon: the Mo-Fr place is closed, the night bar is not open yet.
        found = await events.venue_candidates(session, KALININGRAD, NOON)
        assert [c.venue.osm_id for c in found] == [1, 6]
        assert [c.open_now for c in found] == [None, None]
        evening = datetime(2026, 10, 24, 23, 30)
        late = await events.venue_candidates(session, KALININGRAD, evening)
        assert late[0].venue.osm_id == 3 and late[0].open_now is True
        assert (await events.venue_candidates(session, KALININGRAD, NOON, kinds=["pub"])) == []
        assert (await events.venue_candidates(session, KALININGRAD, NOON, limit=1))[
            0
        ].venue.osm_id == 1
        assert (await events.venue_candidates(session, 1069, NOON)) == []
        assert (await session.scalar(select(func.count()).select_from(Venue))) == 4


async def test_place_snapshot_and_map_links(database: Database) -> None:
    async with database.sessionmaker() as session:
        await events.load_venues(session, Overpass(ok()).source(), [KALININGRAD], 7000, NOW)
        [first, *_] = await events.venue_candidates(session, KALININGRAD, NOON)
    place = events.place_snapshot(first)
    assert place == {
        "name": "Кофейня на углу",
        "address": "Ленина, 1",
        "lat": 54.71,
        "lon": 20.51,
        "link": "https://www.openstreetmap.org/node/1",
        "source": "osm",
        "source_id": "node/1",
    }
    Place.model_validate(place)
    links = events.map_links("Кофейня на углу", "Калининград")
    assert links == {
        "2gis": "https://2gis.ru/search/%D0%9A%D0%BE%D1%84%D0%B5%D0%B9%D0%BD%D1%8F%20%D0%BD%D0%B0%20%D1%83%D0%B3%D0%BB%D1%83%20%D0%9A%D0%B0%D0%BB%D0%B8%D0%BD%D0%B8%D0%BD%D0%B3%D1%80%D0%B0%D0%B4",
        "yandex": "https://yandex.ru/maps/?text=%D0%9A%D0%BE%D1%84%D0%B5%D0%B9%D0%BD%D1%8F%20%D0%BD%D0%B0%20%D1%83%D0%B3%D0%BB%D1%83%20%D0%9A%D0%B0%D0%BB%D0%B8%D0%BD%D0%B8%D0%BD%D0%B3%D1%80%D0%B0%D0%B4",
    }
    assert events.ATTRIBUTION == "© OpenStreetMap contributors"


@pytest.mark.parametrize(
    ("hours", "when", "expected"),
    [
        (None, datetime(2026, 10, 24, 12), None),
        ("24/7", datetime(2026, 10, 24, 3), True),
        ("Mo-Fr 09:00-18:00", datetime(2026, 10, 23, 17, 59), True),  # Friday
        ("Mo-Fr 09:00-18:00", datetime(2026, 10, 23, 18, 0), False),
        ("Mo-Fr 09:00-18:00", datetime(2026, 10, 24, 12), False),  # Saturday
        ("Mo-Fr 09:00-18:00; Sa,Su 10:00-16:00", datetime(2026, 10, 24, 12), True),
        ("Mo-Su 18:00-02:00", datetime(2026, 10, 25, 1, 30), True),  # after midnight
        ("Mo-Su 18:00-02:00", datetime(2026, 10, 25, 2, 30), False),
        ("Mo-Su 09:00-12:00,14:00-18:00", datetime(2026, 10, 24, 13), False),
        ("Mo-Su 09:00-21:00; Sa off", datetime(2026, 10, 24, 12), False),
        ("09:00-21:00", datetime(2026, 10, 24, 12), True),
        ("Mo-Fr 09:00-18:00; PH off", datetime(2026, 10, 24, 12), None),
        ("sunrise-sunset", datetime(2026, 10, 24, 12), None),
        ("Fr-Mo 10:00-12:00", datetime(2026, 10, 25, 11), True),  # a range over the week end
    ],
)
def test_opening_hours(hours: str | None, when: datetime, expected: bool | None) -> None:
    assert events.is_open_at(hours, when) is expected


async def test_the_nightly_job_is_queued_once_a_day(database: Database, settings: Settings) -> None:
    after = datetime(2026, 10, 23, 5, 0, tzinfo=UTC)  # 08:00 in Moscow, past 04:00
    early = datetime(2026, 10, 23, 0, 0, tzinfo=UTC)
    async with database.sessionmaker() as session:
        assert not await local_events.schedule_venues(session, settings, early)
        assert await local_events.schedule_venues(session, settings, after)
        assert not await local_events.schedule_venues(session, settings, after)
        off = settings.model_copy(update={"venues_overpass_urls": " "})
        assert not await local_events.schedule_venues(session, off, after + timedelta(days=1))
        await session.commit()
        jobs = list(
            await session.scalars(select(Job.payload).where(Job.kind == local_events.VENUES_JOB))
        )
        assert jobs == [{"day": "2026-10-23"}]
