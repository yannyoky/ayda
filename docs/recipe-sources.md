# Recipe sources and a curated recipe catalog (issue #122)

English · [Русский](ru/recipe-sources.md)

The M5 cooking quest (#125) offers 2-3 recipes in the morning check-in, asks what is already at home and turns the missing ingredients into a shopping list that can be handed to a friend. This note compares where the recipes can come from. The choice is recorded in ADR 0012.

Research date: 2026-10-22. The cloud environment used for this research cannot reach Russian hosts, so the facts below come from search results and the datasets' public pages, not from reading each licence text in full. Items that need a check are marked **verify**.

## What we need from a source

- Recipes in Russian with **structured ingredients** (an ingredient, an amount, a unit), because the shopping list, the "what is at home" question and allergen checks are done by code.
- A licence that lets us store them in our app, change servings and show them. Free only, no scraping.
- Allergens known per ingredient. The LLM may only pick and phrase recipes; an invented ingredient can miss an allergen.
- Enough everyday dishes for people in any Russian city, with products from an ordinary supermarket.

## Candidates

| Source | Content | Licence | Verdict |
|---|---|---|---|
| Russian recipe sites (Povar.ru, Eda.ru, Russia.food and similar) | Large, good quality | Copyrighted texts and a protected database (Civil Code art. 1334); no public API; scraping breaks their terms | Skip |
| Open datasets on Hugging Face and similar (RecipeNLG, a small Russian set of Mountain Jewish recipes, Russian-tagged community sets) | RecipeNLG is large but English with ingredients as free strings; the small Russian sets are tens of recipes of narrow cuisine with full text instead of parsed ingredients | RecipeNLG: no clear licence; the Russian set is CC BY-NC, which forbids commercial use (**verify** each) | Skip: wrong language or licence, and not structured |
| Wikibooks / community cookbooks in Russian | Some recipes with free-form text | CC BY-SA, which would put our catalog under the same licence; coverage and structure unknown (**verify**) | Skip for now |
| Open Food Facts | Packaged products with barcodes, ingredients and allergens (ODbL) | Open, but it is a product database, not recipes; thin for Russian products (**verify**) | Not a recipe source; may help with allergen data of products later |
| **Our own catalog**, written for Ayda | Everyday dishes in our own words and structure | Ours: a recipe is a list of ingredients and steps, and we write our own text | **Use** |

No open source is both Russian and structured and has a clear licence, so the catalog is our own.

## Recommendation

A curated catalog in the repository, loaded into the database, with these rules:

1. **Format.** One YAML file per recipe in `backend/src/ayda/modules/assistant/recipes/`, checked by a JSON schema in tests:
   - `id`, `title`, `meal` (breakfast, lunch, dinner, snack, dessert), `time_min`, `difficulty` (1-3), `servings` (base), `tags` (for example `vegetarian`, `no_oven`, `budget`, `quick`), `steps` (short, our own words), optional `note`.
   - `ingredients`: a list of `{ingredient, amount, optional}` where `ingredient` is an id from the shared ingredient list.
2. **Ingredient list** (`ingredients.yaml`): `id`, Russian name with forms for the shopping list, `unit` (g, ml, pcs), `aisle` (for ordering the list), `allergens` (gluten, milk, egg, nuts, peanuts, fish, shellfish, soy, sesame, celery, mustard), and `staple` (salt, oil, pepper: assumed at home, pre-ticked).
3. **Code does the work**, never the LLM: filters by meal, time, tags and excluded ingredients or allergens the user named; scales amounts to the number of people; builds the "what is at home" checklist from the ingredient ids and the shopping list from what is not ticked, sorted by aisle. The LLM picks 2-3 recipes among the code's candidates and phrases the offer; its output is validated against a JSON schema and may only contain recipe ids.
4. **Start small:** about 40 everyday recipes (soups, pasta, buckwheat and rice dishes, eggs, salads, baking without exotic tools), reviewed by the owner before release. Any dish added later goes through the same schema test.
5. **Allergens** come from the ingredient list only. The app shows them on the recipe and excludes recipes with an allergen the user named in the check-in; it never claims a dish is safe.
6. **Later:** users add their own recipes, Open Food Facts for packaged products, translations of units and servings for other regions.

## What this costs us

Writing and reviewing about 40 recipes takes real work, and variety grows only as fast as we add dishes. In return the licence is clean, ingredients and allergens are exact, and the shopping hand-off needs no text parsing.
