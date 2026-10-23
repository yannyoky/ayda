from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.realtime import RealtimeDep
from ayda.api.schemas import Coop, RecipeDetail, RecipeOffer, RecipePlanInput, RecipeSuggestInput
from ayda.app import cooking
from ayda.app.day import DayTools

router = APIRouter(tags=["recipes"])


def _now() -> datetime:
    return datetime.now(UTC)


def _tools(request: Request) -> DayTools:
    tools: DayTools = request.app.state.day_tools
    return tools


@router.post("/recipes/suggest", operation_id="suggestRecipes")
async def suggest_recipes(
    body: RecipeSuggestInput,
    user: CurrentUser,
    session: DbSession,
    tools: Annotated[DayTools, Depends(_tools)],
) -> RecipeOffer:
    return await cooking.suggest(session, tools, user, body, _now())


@router.get("/recipes/{recipe_id}", operation_id="getRecipe")
async def get_recipe(
    recipe_id: str, user: CurrentUser, servings: Annotated[int, Query(ge=1, le=8)] = 2
) -> RecipeDetail:
    return cooking.detail(recipe_id, servings)


@router.post("/recipes/{recipe_id}/plan", operation_id="planRecipe", status_code=201)
async def plan_recipe(
    recipe_id: str,
    body: RecipePlanInput,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await cooking.plan(session, realtime, user, recipe_id, body, _now())
