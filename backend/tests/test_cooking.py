"""Cooking quests: recipe suggestions from the catalog and a recipe as a shared plan (M5)."""

import json
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from ayda.app import cooking
from ayda.core.db import Database
from ayda.modules.analytics.models import Event
from ayda.modules.assistant import FakeProvider, ProviderError, recipes
from tests.contract import assert_matches
from tests.helpers import SignedIn
from tests.test_day import TZ, forecast, onboarded, use_tools
from tests.test_feed import befriend

TODAY = datetime.now(ZoneInfo(TZ)).date()
NOW = datetime.combine(TODAY, time(10, 0), ZoneInfo(TZ)).astimezone(UTC)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr("ayda.api.recipes._now", lambda: NOW)
    monkeypatch.setattr("ayda.api.coop._now", lambda: NOW)
    return NOW


def picks(*ids: str) -> str:
    return json.dumps({"items": [{"id": i, "why": f"Хороший выбор: {i}"} for i in ids]})


async def friends(client: httpx.AsyncClient) -> tuple[SignedIn, SignedIn]:
    alice = await onboarded(client, 1001)
    bob = await onboarded(client, 2002)
    await befriend(client, alice, bob)
    return alice, bob


async def suggest(client: httpx.AsyncClient, user: SignedIn, **body: Any) -> httpx.Response:
    return await client.post("/recipes/suggest", json=body, headers=user.headers)


def test_every_recipe_fits_a_plan() -> None:
    rb = recipes.book()
    for recipe in rb.recipes.values():
        need = recipes.shopping_list(recipes.scale(recipe, rb, 8))
        assert len(need) <= cooking.MAX_ITEMS, recipe.id
        assert 0 < len(cooking.step_items(recipe.steps)) <= cooking.MAX_ITEMS, recipe.id


def test_long_sentences_are_cut_to_an_item() -> None:
    [item] = cooking.step_items(["слово " * 40])
    assert len(item) <= cooking.ITEM_CHARS and item.endswith("…")
    assert cooking.step_items(["Один. Два! Три?"]) == ["Один.", "Два!", "Три?"]


async def test_the_assistant_picks_from_the_candidates(
    app: FastAPI, client: httpx.AsyncClient, database: Database
) -> None:
    llm = FakeProvider(answers=[picks("syrniki", "pancakes")])
    use_tools(app, [llm], forecast())
    alice, _ = await friends(client)

    response = await suggest(client, alice, meal="breakfast", allergens=["fish"])
    assert response.status_code == 200, response.text
    assert_matches(response, "suggestRecipes")
    offer = response.json()
    assert offer["source"] == "llm"
    assert [r["id"] for r in offer["recipes"]] == ["syrniki", "pancakes"]
    assert offer["recipes"][0]["why"] == "Хороший выбор: syrniki"
    assert offer["recipes"][0]["allergens"] == ["egg", "gluten", "milk"]
    assert offer["note"] and "аллерген" in offer["note"]

    # The prompt has only catalog data: no user, and only the candidates.
    [(_, prompt)] = llm.calls
    sent = json.loads(prompt)
    assert sent["meal"] == "breakfast"
    assert {c["id"] for c in sent["candidates"]} <= set(recipes.book().recipes)
    assert all(c["id"] and c["title"] for c in sent["candidates"])
    async with database.sessionmaker() as session:
        [logged] = list(
            await session.scalars(select(Event).where(Event.type == "recipes_suggested"))
        )
        assert logged.payload["recipes"] == 2 and logged.payload["allergen_filters"] == 1


async def test_an_id_outside_the_candidates_falls_back_to_code(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    # carbonara is a dinner: not among breakfast candidates.
    use_tools(app, [FakeProvider(answers=[picks("carbonara", "pancakes")] * 3)], forecast())
    alice, _ = await friends(client)
    offer = (await suggest(client, alice, meal="breakfast")).json()
    assert offer["source"] == "code" and len(offer["recipes"]) == 3
    assert all(r["meal"] == "breakfast" and r["why"] is None for r in offer["recipes"])


async def test_without_the_assistant_and_with_filters(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_tools(app, [FakeProvider(answers=[ProviderError("rate_limited")])], forecast())
    alice, _ = await friends(client)
    offer = (
        await suggest(client, alice, meal="dinner", vegetarian=True, allergens=["milk"])
    ).json()
    assert offer["source"] == "code" and offer["recipes"]
    assert all(r["vegetarian"] and "milk" not in r["allergens"] for r in offer["recipes"])

    empty = (await suggest(client, alice, meal="dessert", max_minutes=10, allergens=["egg"])).json()
    assert empty["recipes"] == [] and empty["note"] == cooking.NOTE_NONE


async def test_a_recipe_scales_to_the_servings(client: httpx.AsyncClient) -> None:
    alice = await onboarded(client, 1001)
    response = await client.get("/recipes/carbonara", params={"servings": 4}, headers=alice.headers)
    assert response.status_code == 200, response.text
    assert_matches(response, "getRecipe")
    body = response.json()
    lines = {ln["ingredient"]: ln for ln in body["lines"]}
    assert lines["pasta"]["amount"] == 400 and lines["eggs"]["amount"] == 4
    assert body["recipe"]["allergens"] == ["egg", "gluten", "milk"]
    assert body["steps"] and body["note"]
    assert (await client.get("/recipes/nope", headers=alice.headers)).status_code == 404
    bad = await client.get("/recipes/carbonara", params={"servings": 9}, headers=alice.headers)
    assert bad.status_code == 422


async def test_a_recipe_becomes_a_shopping_and_a_cooking_part(
    client: httpx.AsyncClient, database: Database
) -> None:
    alice, bob = await friends(client)
    response = await client.post(
        "/recipes/pancakes/plan",
        json={"friend_id": bob.user_id, "shopper": "friend", "at_home": ["eggs", "milk"]},
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    assert_matches(response, "planRecipe")
    coop = response.json()
    assert coop["kind"] == "parts" and coop["title"] == "Готовим: Блины на молоке"
    shop, cook = coop["parts"]
    assert shop["title"] == "Купить продукты" and shop["assignee"]["id"] == bob.user_id
    assert [i["text"] for i in shop["items"]] == ["Мука пшеничная: 150 г"]
    assert cook["assignee"]["id"] == alice.user_id and cook["state"] == "locked"
    assert len(cook["items"]) >= 3
    async with database.sessionmaker() as session:
        [logged] = list(await session.scalars(select(Event).where(Event.type == "recipe_planned")))
        assert logged.payload["recipe_id"] == "pancakes" and logged.payload["to_buy"] == 1


async def test_when_everything_is_at_home_both_cook(client: httpx.AsyncClient) -> None:
    alice, bob = await friends(client)
    response = await client.post(
        "/recipes/mug-cake/plan",
        json={
            "friend_id": bob.user_id,
            "shopper": "me",
            "at_home": ["flour", "cocoa", "milk", "eggs"],
        },
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "same"


async def test_plan_rejects_bad_input(client: httpx.AsyncClient) -> None:
    alice, bob = await friends(client)
    stranger = await onboarded(client, 3003)

    def plan(recipe: str, **body: Any) -> Any:
        return client.post(
            f"/recipes/{recipe}/plan",
            json={"friend_id": bob.user_id, "shopper": "me"} | body,
            headers=alice.headers,
        )

    assert (await plan("nope")).status_code == 404
    assert (await plan("pancakes", at_home=["gold"])).status_code == 422
    assert (await plan("pancakes", friend_id=stranger.user_id)).status_code == 403


async def test_a_recipe_can_be_cooked_alone(client: httpx.AsyncClient, database: Database) -> None:
    alice = await onboarded(client, 1001)
    response = await client.post(
        "/recipes/pancakes/quest",
        json={"servings": 2, "at_home": ["eggs", "milk"]},
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    assert_matches(response, "cookRecipeQuest")
    quest = response.json()
    assert quest["title"] == "Готовим: Блины на молоке" and quest["state"] == "taken"
    assert quest["coop_id"] is None
    assert "Купить: Мука пшеничная: 150 г" in quest["description"]
    async with database.sessionmaker() as session:
        [logged] = list(await session.scalars(select(Event).where(Event.type == "recipe_planned")))
        assert logged.payload["solo"] is True and logged.payload["to_buy"] == 1


async def test_cooking_alone_rejects_bad_input(client: httpx.AsyncClient) -> None:
    alice = await onboarded(client, 1001)

    def cook(recipe: str, **body: Any) -> Any:
        return client.post(f"/recipes/{recipe}/quest", json=body, headers=alice.headers)

    assert (await cook("nope")).status_code == 404
    assert (await cook("pancakes", at_home=["gold"])).status_code == 422
    assert (await cook("pancakes", servings=9)).status_code == 422
