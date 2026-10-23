# 0012. A curated recipe catalog of our own

English · [Русский](../ru/decisions/0012-recipe-catalog.md)

## Context
The M5 cooking quest (#125) needs recipes with exact ingredients: the app asks what is at home, builds a shopping list for a "buy groceries" part (ADR 0010) and must not miss an allergen. The comparison is in `docs/recipe-sources.md` (issue #122). No open source is Russian, structured and clearly licensed: recipe sites are protected and cannot be scraped, the open datasets are English, unstructured or non-commercial.

## Decision
- The recipes are a **catalog written for Ayda**, kept in the repository as one YAML file per recipe next to a shared `ingredients.yaml`, validated by a JSON schema in tests and loaded into the database by the `assistant` module. Steps are in our own words. About 40 everyday recipes at the start, reviewed by the owner before release.
- An ingredient has an id, a Russian name with forms, a unit, a shop aisle, allergens and a `staple` flag; a recipe lists `{ingredient, amount, optional}`. Allergens come from ingredients only.
- **Code** filters recipes (meal, time, tags, excluded ingredients and allergens), scales amounts to the number of people, builds the "what is at home" checklist and the shopping list. The **LLM** only picks 2-3 recipe ids from the candidates and phrases the offer; the output is validated against a JSON schema and may contain only ids from the candidates.
- The app shows allergens on a recipe and drops recipes with an allergen the user named; it never says a dish is safe.

## Consequences
The licence is clean and the shopping hand-off needs no text parsing. Variety grows with the work of writing recipes, so the first release is small. A later user-recipes feature and Open Food Facts for packaged products fit the same schema. Fixing the unit and aisle lists is part of #125.
