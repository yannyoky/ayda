# 0010. Shared plans: co-op quests made of parts

English · [Русский](../ru/decisions/0010-shared-plans.md)

## Context
M5 (epic #119) has two owner scenarios: a meetup organized from a chat ("Айда, организуй") and cooking with a shopping hand-off. Both are a co-op quest where people do different things: one meeting at a place and time, or "buy groceries" for one person and "cook" for another, in that order. Today a co-op (ADR 0007, US-18) is one quest that everyone does on their own day; it has no place, no time, no assignee and no order.

## Decision
**One mechanism, two shapes.** A co-op gets a `kind`:
- `same` (all existing co-ops): everyone does the same quest. It gains an optional `place` and `starts_at`, which is all a meetup needs: friends pick a venue and a time, the co-op quest is created, each who accepts gets the quest with them.
- `parts`: the co-op is split into 2-5 parts that can differ in assignee, place, time, checklist and order. Cooking is two parts, "buy groceries" then "cook".

**Data** (in the `quests` schema, next to `coops`):
- `coops` gets `kind`, `place` jsonb null and `starts_at` null. A place is a snapshot: name, address, lat, lon, link, source, source id, price hint. The source is chosen in #121; a snapshot keeps the plan stable if the source changes.
- `coop_parts`: id, coop_id FK cascade, position, title, category, duration_min, place null, starts_at null, assignee_id, opens_after_part_id FK null, day_quest_id FK unique null, state `locked` \| `open` \| `done`, completed_at null.
- `coop_part_items` (checklist): id, part_id FK cascade, position, text varchar(120), done, done_at null. At most 20 per part.
- `coop_handoffs`: part_id PK FK cascade, from_user_id, to_user_id, created_at. A row exists only while a hand-off waits for an answer, so a part has at most one.

**Lifecycle.**
- A part with no `opens_after_part_id` starts `open`; the others start `locked` and have no quest. When a part becomes `open`, its assignee gets a day quest for it (source `coop`, state taken). When the last part before it is completed, the next one opens.
- The assignee completes the part through the ordinary quest completion (photo and visibility as usual). The completion marks the part `done`, opens the parts that waited for it and checks the bonus, all under the locks of ADR 0007 (day pool, then the co-op row).
- Part quests are exempt from the limit of 3 taken quests: a part that opens later in the day must not fail because of it. Accepting a `parts` co-op creates no quest by itself; quests appear as the assigned parts open. In a `same` co-op accepting still counts toward the limit, as before.
- Everything ends with the owner's day (`expires_at`), as now. Plans over several days are not part of M5.

**Participants.** The owner plus up to 3 invited friends, as today. Every part's assignee is the owner or an invited friend; the assistant or the owner chooses assignees when creating the co-op. An invited friend who declines leaves their parts with the owner.

**Hand-off.** The current assignee of a part that is not `done` can offer it to a friend of theirs (`POST .../handoff`) and can withdraw the offer. The friend gets a bot or push message of kind `coop.handoff` and answers accept or decline.
- Accept: the friend joins the co-op if not yet in it (and its chat), becomes the assignee, and if the part is `open`, the previous assignee's quest for it is removed without points or penalty and a new one is created for the friend. Hand-offs can be repeated.
- Decline, withdraw or the end of the day: nothing changes.

**Checklist.** Items are written when the co-op is created (the shopping list comes from the missing ingredients). The assignee ticks and unticks items; the other participants see the ticks live. Unticked items never block completing a part.

**Points.** A part is scored like any quest from its `duration_min` and the visibility chosen at completion. When every part of the co-op is `done` before `expires_at`, each participant who completed at least one part gets one `coop_bonus` ledger row worth `coop_bonus_share` (50%) of what their parts earned, awarded exactly once under the same locks.

**Realtime and API.**
- No new realtime event: every change (part opened or completed, item ticked, hand-off offered or answered) sends the existing `coop.updated` with the co-op id to the participants, and clients reload `GET /coops/{id}`. Push kinds gain `coop.handoff`, which opens the co-op.
- The `Coop` schema gains optional `kind`, `place`, `starts_at` and `parts[]`; a part carries its assignee, state, place, time, `opens_after`, checklist, `my_quest_id` and the pending hand-off (`to`, and whether it is for me). All new fields are optional, so current clients keep working.
- New operations: `POST /coops` (create a co-op directly, for the assistant flows), `PATCH /coops/{id}/parts/{part_id}/items/{item_id}` (tick), `POST /coops/{id}/parts/{part_id}/handoff` with a friend id and `DELETE` on it (withdraw), `POST .../handoff/accept` and `POST .../handoff/decline`.
- The contract changes are added together with the backend in #123, not here, because CI checks that the contract and the implemented routes match.

**Privacy and logging.** Venue and recipe data is public. Checklist and place text are shown only to participants and are never logged. Events are logged with ids and counts only: co-op created, part opened, part completed, part handed off, hand-off answered, bonus awarded.

## Consequences
Existing co-ops, their tests and clients do not change: `same` is the default and the new fields are optional. The Mini App and Android need a parts view and a hand-off dialog (#126). Erasing an account deletes parts and hand-offs it owns or is assigned: a part assigned to an erased user returns to the owner; an erased owner deletes the co-op as now. Because parts are same-day, a plan that spans days (shop in the evening, cook tomorrow) needs a later decision on expiry.
