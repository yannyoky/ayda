"""The "top nearby" picks (ADR 0016): notable events without the user's tastes."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from ayda.app import top_events
from ayda.core.db import Database
from ayda.modules import events
from tests import test_events
from tests.contract import assert_matches
from tests.test_day import onboarded


def soon(
    source_id: str,
    hours: float,
    title: str,
    city_id: int = test_events.KALININGRAD,
    region: str = "39",
    **fields: Any,
) -> events.ListingData:
    start = datetime.now(UTC) + timedelta(hours=hours)
    item = test_events.listing(source_id, timedelta(), city_id, region, title=title)
    return replace(item, starts_at=start, ends_at=start + timedelta(hours=2), **fields)


def test_a_season_covers_its_window_and_the_days_before_it() -> None:
    assert "may" in [s.name for s in top_events.active_seasons(date(2026, 5, 3))]
    assert "may" in [s.name for s in top_events.active_seasons(date(2026, 4, 20))]
    assert "new_year" in [s.name for s in top_events.active_seasons(date(2026, 1, 3))]
    assert top_events.active_seasons(date(2026, 9, 15)) == []


async def test_the_top_is_notable_events_not_tastes(
    client: httpx.AsyncClient, database: Database
) -> None:
    await test_events.seed(
        database,
        [
            soon("quiet", 5, "Камерный вечер", venue="Дом искусств", address="ул. Театральная"),
            soon("fair", 30, "Городская ярмарка", venue="Площадь Победы", is_free=True),
            soon("fair2", 54, "Городская ярмарка", venue="Площадь Победы", is_free=True),
            soon("dear", 6, "Закрытый приём", price_min=9000),
            soon("far", 10, "Праздник у моря", test_events.SVETLOGORSK, is_free=True),
            soon("moscow", 4, "Фестиваль в Москве", test_events.MOSCOW, "77"),
            soon("later", 24 * 20, "Слишком поздно", is_free=True),
        ],
        datetime.now(UTC),
    )
    user = await onboarded(client)

    response = await client.get("/events/top", headers=user.headers)

    assert response.status_code == 200, response.text
    assert_matches(response, "listTopEvents")
    titles = [e["title"] for e in response.json()["items"]]
    assert titles[0] == "Городская ярмарка" and titles.count("Городская ярмарка") == 1
    assert "Фестиваль в Москве" not in titles and "Слишком поздно" not in titles
    assert titles.index("Праздник у моря") < titles.index("Закрытый приём")
    assert response.json()["attribution"].startswith("Афиша")


async def test_a_holiday_lifts_its_own_events(
    client: httpx.AsyncClient, database: Database
) -> None:
    seasons = top_events.active_seasons(date(2026, 5, 5))
    plain = replace(
        test_events.listing("a", timedelta(hours=3), title="Лекция о море"),
        venue=None,
        address=None,
    )
    battle = replace(
        test_events.listing("b", timedelta(hours=3), title="Реконструкция штурма форта"),
        venue="Форт № 5",
    )
    assert (
        top_events.prominence(battle, 1, seasons, True, 0)
        > top_events.prominence(plain, 1, seasons, True, 0) + 4
    )
    assert top_events.prominence(battle, 1, [], True, 0) < top_events.prominence(
        battle, 1, seasons, True, 0
    )


async def test_no_city_means_no_picks(client: httpx.AsyncClient) -> None:
    from tests.helpers import sign_in

    user = await sign_in(client, 3003)
    response = await client.get("/events/top", headers=user.headers)
    assert response.status_code == 200 and response.json()["items"] == []
