"""Events source clients against recorded-style responses (ADR 0008)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from ayda.modules.events import CityRef, KudaGoSource, TimepadSource
from ayda.modules.events.sources import MAX_PAGES, parse_time, price_from_text

KALININGRAD = CityRef(435, "Калининград", "39")
MOSCOW = CityRef(1069, "Москва", "77")
SINCE = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)
UNTIL = SINCE + timedelta(days=3)


def timepad_event(id: int, **overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": id,
        "name": f"Лекция {id}",
        "starts_at": "2026-10-17T19:00:00+0200",
        "ends_at": "2026-10-17T21:00:00+0200",
        "url": f"https://org.timepad.ru/event/{id}/",
        "categories": [{"id": 1, "name": "Наука"}],
        "location": {
            "country": "Россия",
            "city": "Калининград",
            "address": "ул. Театральная, 1",
            "coordinates": [54.71, 20.51],
        },
        "ticket_types": [{"price": 0}],
    }
    return event | overrides


class Recorder:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self.pages[min(len(self.requests), len(self.pages)) - 1])

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self))


async def test_timepad_normalizes_events_and_skips_online_and_other_cities() -> None:
    recorder = Recorder(
        [
            {
                "total": 4,
                "values": [
                    timepad_event(1),
                    timepad_event(
                        2,
                        name="  концерт   у моря ",
                        categories=[{"name": "Концерты"}],
                        ticket_types=[{"price": 1500}, {"price": 700}, {"price": 0}],
                    ),
                    timepad_event(3, location={"country": "Россия", "city": "Без города"}),
                    timepad_event(4, location={"city": "Москва", "address": "Тверская, 1"}),
                ],
            }
        ]
    )

    items = await TimepadSource(recorder.client()).fetch(KALININGRAD, SINCE, UNTIL)

    assert [i.source_id for i in items] == ["1", "2"]
    free, paid = items
    assert free.is_free and free.price_min is None and free.category == "learning"
    assert free.starts_at == datetime(2026, 10, 17, 17, 0, tzinfo=UTC)
    assert free.ends_at == datetime(2026, 10, 17, 19, 0, tzinfo=UTC)
    assert (free.lat, free.lon) == (54.71, 20.51)
    assert free.city_id == 435 and free.region_code == "39"
    assert free.url == "https://org.timepad.ru/event/1/"
    assert paid.title == "Концерт у моря" and paid.category == "city"
    assert not paid.is_free and paid.price_min == 700

    request = recorder.requests[0]
    assert request.url.params["cities"] == "Калининград"
    assert request.url.params["starts_at_min"] == "2026-10-17T08:00:00+0000"
    assert "authorization" not in request.headers


async def test_timepad_pages_and_sends_an_optional_token() -> None:
    full = {"values": [timepad_event(i) for i in range(100)]}
    recorder = Recorder([full, {"values": [timepad_event(500)]}])

    items = await TimepadSource(recorder.client(), token="t0k").fetch(KALININGRAD, SINCE, UNTIL)

    assert len(items) == 101
    assert [r.url.params["skip"] for r in recorder.requests] == ["0", "100"]
    assert recorder.requests[0].headers["authorization"] == "Bearer t0k"


async def test_timepad_stops_after_max_pages() -> None:
    recorder = Recorder([{"values": [timepad_event(i) for i in range(100)]}])

    await TimepadSource(recorder.client()).fetch(KALININGRAD, SINCE, UNTIL)

    assert len(recorder.requests) == MAX_PAGES


async def test_timepad_unknown_price_is_not_free() -> None:
    recorder = Recorder([{"values": [timepad_event(1, ticket_types=[])]}])

    (item,) = await TimepadSource(recorder.client()).fetch(KALININGRAD, SINCE, UNTIL)

    assert not item.is_free and item.price_min is None


async def test_timepad_error_is_raised_for_the_caller() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429)))

    with pytest.raises(httpx.HTTPStatusError):
        await TimepadSource(client).fetch(KALININGRAD, SINCE, UNTIL)


def kudago_event(id: int, dates: list[dict[str, int]], **overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": id,
        "title": "выставка «свет»",
        "dates": dates,
        "place": {
            "id": 9,
            "title": "музей современного искусства",
            "address": "ул. Петровка, 25",
            "coords": {"lat": 55.76, "lon": 37.61},
        },
        "price": "от 500 до 1 200 рублей",
        "is_free": False,
        "site_url": f"https://kudago.com/msk/event/{id}/",
        "categories": ["exhibition"],
    }
    return event | overrides


async def test_kudago_one_listing_per_date_in_the_window() -> None:
    inside = int((SINCE + timedelta(hours=10)).timestamp())
    later = int((SINCE + timedelta(days=1, hours=10)).timestamp())
    before = int((SINCE - timedelta(days=1)).timestamp())
    recorder = Recorder(
        [
            {
                "next": "https://kudago.example/next?page=2",
                "results": [
                    kudago_event(
                        1,
                        [
                            {"start": before, "end": before + 3600},
                            {"start": inside, "end": inside + 5400},
                            {"start": later, "end": later},
                            {"start": -62135433000, "end": 253370754000},
                        ],
                    )
                ],
            },
            {
                "next": None,
                "results": [
                    kudago_event(2, [{"start": inside, "end": inside}], is_free=True, place=None),
                    kudago_event(3, [{"start": inside, "end": inside}], is_free=True, price=""),
                ],
            },
        ]
    )

    items = await KudaGoSource(recorder.client()).fetch(MOSCOW, SINCE, UNTIL)

    assert [i.source_id for i in items] == [f"1:{inside}", f"1:{later}", f"3:{inside}"]
    first, second, free = items
    assert first.title == "Выставка «свет»" and first.venue == "Музей современного искусства"
    assert first.ends_at == first.starts_at + timedelta(minutes=90) and second.ends_at is None
    assert first.price_min == 500 and not first.is_free and first.category == "city"
    assert free.is_free and free.price_min is None
    assert recorder.requests[0].url.params["location"] == "msk"
    assert str(recorder.requests[1].url) == "https://kudago.example/next?page=2"


def test_kudago_covers_only_its_cities() -> None:
    source = KudaGoSource(httpx.AsyncClient())
    assert source.supports(MOSCOW) and not source.supports(KALININGRAD)


@pytest.mark.parametrize(
    ("text", "price"),
    [("от 500 до 1 200 рублей", 500), ("1500 руб.", 1500), ("бесплатно", None), ("", None)],
)
def test_price_from_text(text: str, price: int | None) -> None:
    assert price_from_text(text) == price


def test_parse_time_accepts_both_offsets() -> None:
    expected = datetime(2026, 10, 17, 16, 0, tzinfo=UTC)
    assert parse_time("2026-10-17T19:00:00+0300") == expected
    assert parse_time("2026-10-17T19:00:00+03:00") == expected
