# 0017. A taste profile learned from what the user does with quests

English · [Русский](../ru/decisions/0017-learned-taste.md)

## Context
ADR 0015 ranks events by the request, the check-in and the goals. The owner (2026-10-23) wants a stronger per-user recommendation: the assistant should offer what the user is interested in judging by their earlier choices. Every quest the user took, finished or swapped away is already stored, with its category and, for events, its title.

## Decision
- **Source.** The user's quests of the last 60 days that were taken, finished or swapped away (`quests.day_quests`). Quests that were only offered say nothing and are left out. Nothing new is stored and nothing leaves the database: the profile is computed on demand from rows the user already has.
- **Weights.** A finished quest counts +3, a taken one +1. A swapped-away quest counts -2.5 when the reason is "не хочу" (`dont_want`), -0.5 for "нет времени" (`no_time`), and 0 for "не могу" (`cant`), which says nothing about taste. Each signal halves every 30 days.
- **Profile.** Per quest category, the weighted sum is squeezed into (-1, 1) by `v / (|v| + 4)`, so a few signals stay modest and the share never reaches 1. For event quests the same is done per stem of the title (first 4 letters of its words), so a finished "Джазовый вечер" lifts later "Вечер джаза".
- **Use.** The interest score of ADR 0015 adds 2 × the category share and up to ±2 for liked or disliked title stems. The effect applies to event quests in the pool and to the assistant's event search. A word the user asks for (×3) still beats the learned taste.
- **Not used.** The "top nearby" block (ADR 0016) is tastes-free on purpose. The catalog quest ranking is not changed here.
- **Privacy.** No text of the check-in is read. No new personal data is collected or logged; the profile is never sent to an LLM.

## Consequences
A new user has no signals, so the profile is empty and ranking falls back to ADR 0015. A user who finishes only one kind of quest will see more of it; the saturation and the decay limit this, and the explicit request always wins. The profile is recomputed on each check-in and event search, which costs one indexed query over at most 60 days of one user's quests. Interests the user declares in the profile (free-text tags) are the next step and will feed the same score.
