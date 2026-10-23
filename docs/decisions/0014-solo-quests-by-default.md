# 0014. Quests are solo by default, shared on demand

English · [Русский](../ru/decisions/0014-solo-quests-by-default.md)

## Context
M5 (ADR 0010, 0012) made cooking a shared plan: "Приготовить вместе" on the main screen, a friend was required, and the plan split shopping and cooking between two people. The owner (2026-10-23) does not want a quest that cannot be done alone: every quest is solo by default and any quest can be made shared.

## Decision
- A quest is always a normal day quest of its owner. Making it shared is a separate step that every quest already has (the invite button, ADR 0007 and 0010); nothing is shared until the owner invites someone.
- Cooking follows the same rule. A recipe becomes an own quest, "Готовим: <recipe>", taken right away, with the recipe, allergens and what to buy in its description (`POST /recipes/{id}/quest`). The plan with a friend that splits shopping and cooking (`POST /recipes/{id}/plan`, ADR 0012) stays as an option, chosen after the recipe, not the default.
- The main screen has no cooking entry. Recipes are offered by the assistant chat ("suggest_dishes", ADR 0013) and open from its cards.

## Consequences
One new operation and no schema change: the quest is an own quest, so the daily limit of taken quests and the scoring apply as for any other. The shopping list of a solo recipe is text in the description, not a checklist; a checklist exists only in a plan with a friend. Clients drop the main-screen button and let the recipe sheet cook alone.
