from pathlib import Path

import pytest

from ayda.modules.assistant import recipes
from ayda.modules.assistant.recipes import Line


def test_catalog_loads_and_is_big_enough() -> None:
    rb = recipes.book()
    assert len(rb.recipes) >= 40
    meals = {r.meal for r in rb.recipes.values()}
    assert {"breakfast", "lunch", "dinner"} <= meals


def test_every_recipe_has_a_required_non_staple_ingredient() -> None:
    rb = recipes.book()
    for recipe in rb.recipes.values():
        assert any(
            not i.optional and not rb.ingredients[i.ingredient].staple for i in recipe.ingredients
        ), recipe.id


def test_every_ingredient_is_used() -> None:
    rb = recipes.book()
    used = {i.ingredient for r in rb.recipes.values() for i in r.ingredients}
    assert set(rb.ingredients) == used


def test_derived_allergens() -> None:
    rb = recipes.book()
    assert recipes.allergens(rb.recipes["carbonara"], rb.ingredients) == ["egg", "gluten", "milk"]
    assert recipes.allergens(rb.recipes["shrimp-garlic-pasta"], rb.ingredients) == [
        "gluten",
        "shellfish",
    ]


def test_vegetarian_flag() -> None:
    rb = recipes.book()
    assert recipes.is_vegetarian(rb.recipes["greek-salad"], rb.ingredients)
    assert not recipes.is_vegetarian(rb.recipes["carbonara"], rb.ingredients)


def test_candidates_filters() -> None:
    rb = recipes.book()
    quick = recipes.candidates(rb, meal="breakfast", max_minutes=10)
    assert quick
    assert all(r.meal == "breakfast" and r.minutes <= 10 for r in quick)
    assert [r.minutes for r in quick] == sorted(r.minutes for r in quick)

    no_gluten = recipes.candidates(rb, avoid_allergens=["gluten"], limit=100)
    assert all("gluten" not in recipes.allergens(r, rb.ingredients) for r in no_gluten)
    assert "carbonara" not in {r.id for r in no_gluten}

    veg = recipes.candidates(rb, vegetarian=True, limit=100)
    assert veg
    assert all(recipes.is_vegetarian(r, rb.ingredients) for r in veg)

    no_eggs = recipes.candidates(rb, avoid_ingredients=["eggs"], limit=100)
    assert all("eggs" not in {i.ingredient for i in r.ingredients} for r in no_eggs)
    assert len(recipes.candidates(rb, limit=3)) == 3


def test_scale_rounds_to_kitchen_amounts() -> None:
    rb = recipes.book()
    lines = {ln.ingredient: ln for ln in recipes.scale(rb.recipes["carbonara"], rb, 3)}
    assert lines["pasta"].amount == 300
    assert lines["bacon"].amount == 180
    assert lines["eggs"].amount == 3
    one = {ln.ingredient: ln for ln in recipes.scale(rb.recipes["carbonara"], rb, 1)}
    assert one["eggs"].amount == 1
    assert one["salt"].amount == 1


def test_shopping_list_skips_home_staples_and_optional() -> None:
    rb = recipes.book()
    lines = recipes.scale(rb.recipes["pancakes"], rb, 2)
    need = recipes.shopping_list(lines)
    ids = {ln.ingredient for ln in need}
    assert {"flour", "milk", "eggs"} <= ids
    assert not ids & {"salt", "oil", "sugar"}
    assert "sour_cream" not in ids
    at_home = recipes.shopping_list(lines, at_home=["milk", "eggs"])
    assert {ln.ingredient for ln in at_home} == {"flour"}


def test_shopping_list_is_grouped_by_aisle() -> None:
    rb = recipes.book()
    need = recipes.shopping_list(recipes.scale(rb.recipes["chicken-plov"], rb, 2))
    order = [recipes.AISLES.index(ln.aisle) for ln in need]
    assert order == sorted(order)


def test_format_line_fits_a_part_item() -> None:
    line = Line("x", "Помидоры", 250.0, "g", "produce", False, False)
    assert recipes.format_line(line) == "Помидоры: 250 г"
    rb = recipes.book()
    for recipe in rb.recipes.values():
        for ln in recipes.scale(recipe, rb, 12):
            assert len(recipes.format_line(ln)) <= 120


def _write(directory: Path, ingredients: str, recipe: str) -> None:
    (directory / "recipes").mkdir()
    (directory / "ingredients.yaml").write_text(ingredients, encoding="utf-8")
    (directory / "recipes" / "dish.yaml").write_text(recipe, encoding="utf-8")


ING = """
ingredients:
  - {id: a, name: Aaa, unit: g, aisle: produce}
  - {id: b, name: Bbb, unit: g, aisle: produce}
"""


def test_unknown_ingredient_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ING,
        "id: dish\ntitle: Dish\nmeal: lunch\nminutes: 10\nservings: 2\n"
        "ingredients: [{ingredient: a, amount: 1}, {ingredient: zzz, amount: 1}]\nsteps: [x]\n",
    )
    with pytest.raises(ValueError, match="unknown ingredient"):
        recipes.load_book(tmp_path)


def test_file_name_must_match_id(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ING,
        "id: other\ntitle: Dish\nmeal: lunch\nminutes: 10\nservings: 2\n"
        "ingredients: [{ingredient: a, amount: 1}, {ingredient: b, amount: 1}]\nsteps: [x]\n",
    )
    with pytest.raises(ValueError, match="does not match"):
        recipes.load_book(tmp_path)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ING,
        "id: dish\ntitle: Dish\nmeal: lunch\nminutes: 10\nservings: 2\nkcal: 5\n"
        "ingredients: [{ingredient: a, amount: 1}, {ingredient: b, amount: 1}]\nsteps: [x]\n",
    )
    with pytest.raises(ValueError):
        recipes.load_book(tmp_path)
