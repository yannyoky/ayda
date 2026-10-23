"""Cooking quests (M5, ADR 0012): recipes picked from our catalog, planned as a shared plan.

Code filters the catalog, scales amounts and builds the lists; the assistant only picks 2-3 ids
from the candidates and says why. Nothing about the users goes into the prompt, and the app
never says a dish is safe: allergens are shown and named ones filter recipes out.
"""

import re
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import (
    Coop,
    CoopCreateInput,
    CoopPartInput,
    RecipeCard,
    RecipeDetail,
    RecipeLine,
    RecipeOffer,
    RecipePlanInput,
    RecipeSuggestInput,
)
from ayda.app import coop as coop_app
from ayda.app.day import DayTools
from ayda.core.problems import Problem
from ayda.core.realtime import Realtime
from ayda.modules import analytics, assistant, auth
from ayda.modules.analytics import EventType
from ayda.modules.assistant import recipes

CANDIDATES = 12
PICKS = 3
LLM_DEADLINE_S = 12.0
SHOPPING_MINUTES = 40
MAX_ITEMS = 20
ITEM_CHARS = 120

NOTE_NONE = "Подходящих рецептов нет. Попробуй убрать часть условий."
NOTE_ALLERGENS = (
    "Рецепты с названными аллергенами убраны. Состав продуктов всё равно проверяй на упаковке."
)
NOTE_DETAIL = (
    "Аллергены указаны по ингредиентам из рецепта. Состав покупных продуктов проверяй сам."
)
ALLERGENS_RU = {
    "gluten": "глютен",
    "milk": "молоко",
    "egg": "яйца",
    "fish": "рыба",
    "shellfish": "морепродукты",
    "nuts": "орехи",
    "peanut": "арахис",
    "soy": "соя",
    "sesame": "кунжут",
}


def recipe_card(
    recipe: recipes.Recipe, rb: recipes.RecipeBook, why: str | None = None
) -> RecipeCard:
    return RecipeCard(
        id=recipe.id,
        title=recipe.title,
        meal=recipe.meal,
        minutes=recipe.minutes,
        servings=recipe.servings,
        allergens=recipes.allergens(recipe, rb.ingredients),
        vegetarian=recipes.is_vegetarian(recipe, rb.ingredients),
        why=why,
    )


def _find(recipe_id: str) -> recipes.Recipe:
    found = recipes.book().recipes.get(recipe_id)
    if found is None:
        raise Problem(404, "recipe-not-found", detail="Такого рецепта нет")
    return found


async def suggest(
    session: AsyncSession,
    tools: DayTools,
    user: auth.User,
    body: RecipeSuggestInput,
    now: datetime,
) -> RecipeOffer:
    rb = recipes.book()
    found = recipes.candidates(
        rb,
        meal=body.meal,
        max_minutes=body.max_minutes,
        avoid_allergens=body.allergens,
        vegetarian=body.vegetarian,
        limit=CANDIDATES,
    )
    why: dict[str, str] = {}
    source = "code"
    chosen = found[:PICKS]
    if len(found) >= 2:
        summary: list[dict[str, object]] = [
            {"id": r.id, "title": r.title, "minutes": r.minutes, "meal": r.meal, "tags": r.tags}
            for r in found
        ]
        result = await assistant.pick_recipes(
            tools.assistant, body.meal, summary, deadline_s=LLM_DEADLINE_S
        )
        if result is not None:
            by_id = {r.id: r for r in found}
            chosen = [by_id[i.id] for i in result.value.items]
            why = {i.id: i.why for i in result.value.items}
            source = "llm"
    note = NOTE_NONE if not found else (NOTE_ALLERGENS if body.allergens else None)
    offer = RecipeOffer(
        source=source,  # pyright: ignore[reportArgumentType]
        recipes=[recipe_card(r, rb, why.get(r.id)) for r in chosen],
        note=note,
    )
    await analytics.record(
        session,
        EventType.RECIPES_SUGGESTED,
        user.id,
        {
            "source": source,
            "meal": body.meal,
            "candidates": len(found),
            "recipes": len(offer.recipes),
            "allergen_filters": len(body.allergens),
        },
        occurred_at=now,
    )
    await session.commit()
    return offer


def detail(recipe_id: str, servings: int) -> RecipeDetail:
    rb = recipes.book()
    recipe = _find(recipe_id)
    lines = recipes.scale(recipe, rb, servings)
    return RecipeDetail(
        recipe=recipe_card(recipe, rb),
        servings=servings,
        lines=[RecipeLine.model_validate(ln, from_attributes=True) for ln in lines],
        steps=recipe.steps,
        note=NOTE_DETAIL,
    )


def step_items(steps: list[str]) -> list[str]:
    """The cook's checklist: one item per sentence, so each fits an item of a part."""
    items = [s for step in steps for s in re.split(r"(?<=[.!?])\s+", step.strip()) if s]
    return [i if len(i) <= ITEM_CHARS else i[: ITEM_CHARS - 1].rstrip() + "…" for i in items]


async def plan(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    recipe_id: str,
    body: RecipePlanInput,
    now: datetime,
) -> Coop:
    """A shared plan for a recipe: one friend shops, the other cooks. When nothing needs
    buying, both simply cook it."""
    rb = recipes.book()
    recipe = _find(recipe_id)
    unknown = [i for i in body.at_home if i not in {x.ingredient for x in recipe.ingredients}]
    if unknown:
        raise Problem(422, "validation-failed", detail="Это не ингредиент рецепта")
    lines = recipes.scale(recipe, rb, body.servings)
    need = recipes.shopping_list(lines, body.at_home)
    found_allergens = recipes.allergens(recipe, rb.ingredients)
    description = f"Рецепт «{recipe.title}», порций: {body.servings}."
    if found_allergens:
        description += " Аллергены: " + ", ".join(ALLERGENS_RU[a] for a in found_allergens) + "."
    title = f"Готовим: {recipe.title}"[:120]
    parts: list[CoopPartInput] | None = None
    duration = recipe.minutes
    if need:
        shopper = user.id if body.shopper == "me" else body.friend_id
        cook = body.friend_id if body.shopper == "me" else user.id
        parts = [
            CoopPartInput(
                title="Купить продукты",
                category="home",
                duration_min=SHOPPING_MINUTES,
                assignee_id=shopper,
                items=[recipes.format_line(ln) for ln in need][:MAX_ITEMS],
            ),
            CoopPartInput(
                title=f"Приготовить: {recipe.title}"[:120],
                category="home",
                duration_min=recipe.minutes,
                assignee_id=cook,
                opens_after=0,
                items=step_items(recipe.steps)[:MAX_ITEMS],
            ),
        ]
        duration = min(480, recipe.minutes + SHOPPING_MINUTES)
    created = await coop_app.create_plan(
        session,
        realtime,
        user,
        CoopCreateInput(
            title=title,
            description=description,
            category="home",
            duration_min=max(5, duration),
            outdoor=False,
            starts_at=body.starts_at,
            friend_ids=[body.friend_id],
            parts=parts,
        ),
        now,
    )
    await analytics.record(
        session,
        EventType.RECIPE_PLANNED,
        user.id,
        {
            "coop_id": created.id,
            "recipe_id": recipe.id,
            "servings": body.servings,
            "to_buy": len(need),
        },
        occurred_at=now,
    )
    await session.commit()
    return created
