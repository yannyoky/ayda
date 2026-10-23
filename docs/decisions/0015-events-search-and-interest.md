# 0015. Events search in the chat and ranking by interest

English · [Русский](../ru/decisions/0015-events-search-and-interest.md)

## Context
Since M3 (ADR 0008) the worker loads listings for the next 3 days, for the users' own cities and the largest city of each of their regions. Up to 2 events go into the pool in random order. The owner (2026-10-23) wants two things. First, the assistant should find events on request: in the user's own town by default, and across the whole region, so a user in Kaliningrad also sees the rest of Kaliningrad Oblast. Second, results should be sorted by how interesting they are, and the check-in should bring events that fit it into the pool.

## Decision
- **Region-wide loading.** For every region with users, the nightly `events.ingest` loads the users' own cities plus the 15 largest towns of the region by population (`REGION_TOWNS`). The window grows from 3 to 7 days, so "this weekend" and "next week" can be answered. Sources stay Timepad and KudaGo with no scraping. A regional portal is added only through an open API or feed, as a new source.
- **A chat action.** ADR 0013 gains `find_events` with an optional `query` (up to 60 characters), `place` (a town), `when` (`today`, `tomorrow`, `weekend`, `week`) and `category`. Without an LLM, code recognises requests about listings, concerts, exhibitions, theatre and so on by keywords, and reads the town ("в Светлогорске") and the day from the text. Code builds the card: up to 5 events, one per title, with time, venue, town, distance, price and link, plus the attribution "Афиша: Timepad и KudaGo".
- **Where.** By default the search covers the user's whole region. A named town of the same region narrows it to that town. A town of another region gets a note that only the user's region is collected. An unknown town falls back to the user's own region.
- **Interest is scored by code.** Each candidate's score is the sum of:
  - words of the request (stem matches in the title) ×3;
  - words of the check-in ×1, at most 3;
  - the asked category +2;
  - a category matching the user's goals +1;
  - free entry +0.5;
  - the user's own town +0.5, while other towns lose up to 1.5 by distance (1 per 100 km);
  - starting later costs up to 1.

  The chat sorts by this score. When the best result of a query still scores under 3, the card says nothing exact was found and shows what else is on. The pool sorts event candidates by the same score with the check-in and goals, and takes the best one plus one random event among the next four, so the pool stays varied.
- **The LLM** only fills the action. It never sees the listings or ranks them.

## Consequences
The ingest makes about 16 Timepad requests per region a night instead of 1, still small. 7 days of listings for many towns make the table bigger, and old rows are still dropped 2 days after they end. Word stems are a rough match ("джаз" finds "Джазовый вечер" but not "саксофон"). A learned interest profile from past choices (the `events` log) and a separate "top nearby" pick of big public events are the next steps. They will reuse this score as a baseline.
