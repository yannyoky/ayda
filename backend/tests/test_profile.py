import httpx

from tests.contract import assert_matches
from tests.helpers import sign_in

KALININGRAD = 435


async def test_city_search_by_name_prefers_prefix_and_population(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)

    response = await client.get("/cities", params={"query": "калинин"}, headers=me.headers)

    assert response.status_code == 200
    assert_matches(response, "searchCities")
    first = response.json()["items"][0]
    assert first == {
        "id": KALININGRAD,
        "name": "Калининград",
        "region_name": "Калининградская область",
        "timezone": "Europe/Kaliningrad",
    }


async def test_city_search_by_yo_letter(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    response = await client.get("/cities", params={"query": "королев"}, headers=me.headers)
    assert [c["name"] for c in response.json()["items"]] == ["Королёв"]


async def test_nearest_city_by_coordinates(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)

    response = await client.get(
        "/cities", params={"lat": 54.71, "lon": 20.51, "limit": 3}, headers=me.headers
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Калининград"
    assert len(response.json()["items"]) == 3


async def test_city_search_needs_query_or_point(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    response = await client.get("/cities", params={"lat": 54.7}, headers=me.headers)
    assert response.status_code == 422
    assert_matches(response, "searchCities")


async def test_onboarding_flow(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    h = me.headers

    blocked = await client.post("/me/onboarding/complete", headers=h)
    assert blocked.status_code == 409
    assert_matches(blocked, "completeOnboarding")

    consent = await client.post("/me/consents", json={"version": "2026-10-23"}, headers=h)
    assert consent.status_code == 204
    assert_matches(consent, "acceptConsent")
    again = await client.post("/me/consents", json={"version": "2026-10-23"}, headers=h)
    assert again.status_code == 204

    no_city = await client.post("/me/onboarding/complete", headers=h)
    assert no_city.status_code == 409
    assert no_city.json()["type"].endswith("city-required")

    updated = await client.patch(
        "/me/profile",
        json={
            "city_id": KALININGRAD,
            "theme": "plum",
            "reminders": {"morning_at": "08:30", "evening_at": None},
        },
        headers=h,
    )
    assert updated.status_code == 200
    assert_matches(updated, "updateProfile")
    body = updated.json()
    assert body["city"]["name"] == "Калининград"
    assert body["timezone"] == "Europe/Kaliningrad"
    assert body["theme"] == "plum"
    assert body["reminders"] == {"morning_at": "08:30", "evening_at": None}
    assert body["consent_required"] is None

    done = await client.post("/me/onboarding/complete", headers=h)
    assert done.status_code == 200
    assert_matches(done, "completeOnboarding")
    assert done.json()["onboarded"] is True


async def test_profile_update_validation(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    bodies = ({}, {"city_id": 999999}, {"theme": "neon"}, {"reminders": {"morning_at": "25:00"}})
    for body in bodies:
        response = await client.patch("/me/profile", json=body, headers=me.headers)
        assert response.status_code == 422, body
        assert_matches(response, "updateProfile")


async def test_unknown_consent_version_is_422(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    response = await client.post("/me/consents", json={"version": "1999"}, headers=me.headers)
    assert response.status_code == 422


async def test_interests(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)

    catalog = await client.get("/interests", headers=me.headers)
    assert_matches(catalog, "listInterests")
    codes = [i["code"] for i in catalog.json()["items"]]
    assert "sport" in codes and "music" in codes

    saved = await client.put(
        "/me/interests",
        json={"codes": ["sport", "project"], "tags": ["  Джаз ", "стендап", "джаз"]},
        headers=me.headers,
    )
    assert saved.status_code == 200
    assert_matches(saved, "setMyInterests")
    listed = await client.get("/me/interests", headers=me.headers)
    assert_matches(listed, "listMyInterests")
    assert listed.json() == {"codes": ["project", "sport"], "tags": ["джаз", "стендап"]}

    skipped = await client.put("/me/interests", json={"codes": [], "tags": []}, headers=me.headers)
    assert skipped.json() == {"codes": [], "tags": []}

    bad_bodies = (
        {"codes": ["nope"], "tags": []},
        {"codes": codes[:9], "tags": []},
        {"codes": ["sport", "sport"], "tags": []},
        {"codes": [], "tags": ["a", "b", "c", "d", "e", "f"]},
        {"codes": [], "tags": ["x" * 31]},
        {"codes": [], "tags": ["see http://spam.ru"]},
    )
    for bad in bad_bodies:
        response = await client.put("/me/interests", json=bad, headers=me.headers)
        assert response.status_code == 422, bad
        assert_matches(response, "setMyInterests")


async def test_habits_are_stored_as_worded(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)
    other = await sign_in(client, telegram_id=2002, name="Петя")

    created = await client.post(
        "/me/habits", json={"direction": "less", "text": "Дота по ночам"}, headers=me.headers
    )
    assert created.status_code == 201
    assert_matches(created, "addMyHabit")
    habit = created.json()
    assert habit["text"] == "Дота по ночам"

    listed = await client.get("/me/habits", headers=me.headers)
    assert_matches(listed, "listMyHabits")
    assert listed.json()["items"] == [habit]
    assert (await client.get("/me/habits", headers=other.headers)).json()["items"] == []

    foreign = await client.delete(f"/me/habits/{habit['id']}", headers=other.headers)
    assert foreign.status_code == 404
    assert_matches(foreign, "deleteMyHabit")
    deleted = await client.delete(f"/me/habits/{habit['id']}", headers=me.headers)
    assert deleted.status_code == 204
    assert_matches(deleted, "deleteMyHabit")
