# 0018. Interests instead of goals

English · [Русский](../ru/decisions/0018-interests-instead-of-goals.md)

## Context
Onboarding asked for 1-5 goals from a fixed list ("Больше двигаться", "Чаще видеться с людьми"). Goals ranked catalog quests but said little about events: a goal cannot tell the app that someone likes jazz or stand-up. The owner (2026-10-23) wants interests instead of goals, so the assistant, the quest pool and the events block follow what the user actually likes. Own habits ("want more", "want less") stay: they are not tastes but things the user wants to change, and later reminders rest on them.

## Decision
- **A catalog of 16 interests** in code (`habits/interests.py`): sport, outdoors, city and history, music, theatre and cinema, art, humor, lectures, books, food and cooking, games, meeting people, family, quiet rest, own project, home order. Each has a stable code, a title, the quest and event categories it serves, and word stems of event titles that point at it.
- **Own words.** Besides the catalog the user can add up to 5 words of their own ("джаз", "настолки"), up to 30 characters each, lower-cased, without links or addresses. They match event titles by stem and are never sent to an LLM.
- **A pick.** Up to 8 catalog interests plus up to 5 own words, on onboarding (optional) and in the profile. API: `GET/PUT /me/interests` and `GET /interests` replace `/me/goals` and `/goals`.
- **Use.**
  - Catalog quests carry `interest_codes`, and the pool ranks them by overlap as it did with goals.
  - The interest score of ADR 0015 adds +1 for an event in a category of the user's interests and +1.5 per matching title word (at most two), from the catalog words and the user's own words. The learned taste of ADR 0017 stays on top.
  - The assistant receives the catalog codes in place of goal codes.
- **Migration.** Saved goals become the interests they served (for example "Больше двигаться" becomes sport and outdoors); quest templates are converted the same way. The old table and endpoints are removed, so the Mini App and the Android app are updated together and the old Android build should be replaced after the deploy.

## Consequences
The user states tastes in their own words, which helps events most, and the same list feeds quests. Interests that no catalog quest serves (music, theatre, art, humor, family) work through events and the assistant only. The catalog is a first guess and will be tuned by what people pick. Goals like "sleep better" or "less stress" are gone as such; they live on in quiet rest and in the habits.
