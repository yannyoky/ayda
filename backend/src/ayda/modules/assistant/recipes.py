"""Recipe catalog (ADR 0012): our own YAML recipes; code filters, scales and builds lists.

The LLM never sees amounts or allergens: it only picks ids from `candidates`.
"""

import math
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

RECIPES_DIR = Path(__file__).parent / "data"

Unit = Literal["g", "ml", "pcs", "clove", "slice", "tbsp", "tsp", "pinch"]
Aisle = Literal[
    "produce", "dairy", "meat", "fish", "grocery", "bakery", "frozen", "drinks", "other"
]
AISLES: tuple[Aisle, ...] = (
    "produce",
    "bakery",
    "dairy",
    "meat",
    "fish",
    "grocery",
    "frozen",
    "drinks",
    "other",
)
Allergen = Literal["gluten", "milk", "egg", "fish", "shellfish", "nuts", "peanut", "soy", "sesame"]
Meal = Literal["breakfast", "lunch", "dinner", "snack", "dessert"]
Diet = Literal["meat", "fish"]

_WHOLE_UNITS = {"pcs", "clove", "slice"}


class Ingredient(BaseModel, extra="forbid"):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=60)
    unit: Unit
    aisle: Aisle
    allergens: list[Allergen] = []
    staple: bool = False
    diet: Diet | None = None


class RecipeIngredient(BaseModel, extra="forbid"):
    ingredient: str
    amount: float = Field(gt=0)
    optional: bool = False


class Recipe(BaseModel, extra="forbid"):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=3, max_length=80)
    meal: Meal
    minutes: int = Field(ge=5, le=240)
    servings: int = Field(ge=1, le=12)
    tags: list[str] = []
    ingredients: list[RecipeIngredient] = Field(min_length=2)
    steps: list[str] = Field(min_length=1, max_length=12)


class RecipeBook(BaseModel, extra="forbid"):
    ingredients: dict[str, Ingredient]
    recipes: dict[str, Recipe]

    @model_validator(mode="after")
    def _references(self) -> "RecipeBook":
        for recipe in self.recipes.values():
            seen = [i.ingredient for i in recipe.ingredients]
            if len(set(seen)) != len(seen):
                raise ValueError(f"{recipe.id}: an ingredient is listed twice")
            for ref in seen:
                if ref not in self.ingredients:
                    raise ValueError(f"{recipe.id}: unknown ingredient {ref}")
            if any(len(s) > 400 for s in recipe.steps):
                raise ValueError(f"{recipe.id}: a step is longer than 400 characters")
        return self


@dataclass(frozen=True, slots=True)
class Line:
    ingredient: str
    name: str
    amount: float
    unit: Unit
    aisle: Aisle
    optional: bool
    staple: bool


def load_book(directory: Path = RECIPES_DIR) -> RecipeBook:
    with (directory / "ingredients.yaml").open(encoding="utf-8") as f:
        ingredients = {
            i["id"]: Ingredient.model_validate(i) for i in yaml.safe_load(f)["ingredients"]
        }
    recipes: dict[str, Recipe] = {}
    for path in sorted((directory / "recipes").glob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            recipe = Recipe.model_validate(yaml.safe_load(f))
        if recipe.id != path.stem:
            raise ValueError(f"{path.name}: id {recipe.id} does not match the file name")
        recipes[recipe.id] = recipe
    return RecipeBook(ingredients=ingredients, recipes=recipes)


@cache
def book() -> RecipeBook:
    return load_book()


def allergens(recipe: Recipe, ingredients: dict[str, Ingredient]) -> list[Allergen]:
    """Allergens of all ingredients, optional ones included: better a warning than a miss."""
    found = {a for i in recipe.ingredients for a in ingredients[i.ingredient].allergens}
    return sorted(found)  # pyright: ignore[reportReturnType]


def is_vegetarian(recipe: Recipe, ingredients: dict[str, Ingredient]) -> bool:
    return all(ingredients[i.ingredient].diet is None for i in recipe.ingredients)


def candidates(
    rb: RecipeBook,
    *,
    meal: Meal | None = None,
    max_minutes: int | None = None,
    avoid_allergens: Collection[str] = (),
    avoid_ingredients: Collection[str] = (),
    vegetarian: bool = False,
    limit: int = 12,
) -> list[Recipe]:
    """Recipes that fit the filters, shortest first; the LLM picks from these."""
    avoid = set(avoid_allergens)
    skip = set(avoid_ingredients)
    found: list[Recipe] = []
    for recipe in rb.recipes.values():
        if meal is not None and recipe.meal != meal:
            continue
        if max_minutes is not None and recipe.minutes > max_minutes:
            continue
        if skip & {i.ingredient for i in recipe.ingredients}:
            continue
        if avoid & set(allergens(recipe, rb.ingredients)):
            continue
        if vegetarian and not is_vegetarian(recipe, rb.ingredients):
            continue
        found.append(recipe)
    found.sort(key=lambda r: (r.minutes, r.id))
    return found[:limit]


def _round(amount: float, unit: Unit) -> float:
    if unit in _WHOLE_UNITS:
        return float(max(1, math.ceil(amount - 1e-9)))
    if unit in ("g", "ml"):
        return float(max(5, round(amount / 5) * 5))
    if unit == "pinch":
        return max(1.0, round(amount))
    return max(0.5, round(amount * 2) / 2)


def scale(recipe: Recipe, rb: RecipeBook, servings: int) -> list[Line]:
    """Ingredient lines for `servings` people, amounts rounded to what a kitchen measures."""
    factor = servings / recipe.servings
    lines: list[Line] = []
    for item in recipe.ingredients:
        ing = rb.ingredients[item.ingredient]
        lines.append(
            Line(
                ingredient=ing.id,
                name=ing.name,
                amount=_round(item.amount * factor, ing.unit),
                unit=ing.unit,
                aisle=ing.aisle,
                optional=item.optional,
                staple=ing.staple,
            )
        )
    return lines


def shopping_list(lines: Iterable[Line], at_home: Collection[str] = ()) -> list[Line]:
    """What to buy: required lines not at home; staples count as at home unless unchecked."""
    home = set(at_home)
    need = [ln for ln in lines if not ln.optional and not ln.staple and ln.ingredient not in home]
    return sorted(need, key=lambda ln: (AISLES.index(ln.aisle), ln.name))


def format_line(line: Line) -> str:
    """One checklist row, within the 120 characters of a part item."""
    amount = f"{line.amount:g}"
    labels = {
        "g": "г",
        "ml": "мл",
        "pcs": "шт",
        "clove": "зубч.",
        "slice": "ломт.",
        "tbsp": "ст. л.",
        "tsp": "ч. л.",
        "pinch": "щепотка",
    }
    return f"{line.name}: {amount} {labels[line.unit]}"
