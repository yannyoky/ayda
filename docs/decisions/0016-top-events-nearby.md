# 0016. "Top nearby": notable events without the user's tastes

English · [Русский](../ru/decisions/0016-top-events-nearby.md)

## Context
ADR 0015 ranks events by what the user is interested in. The owner (2026-10-23) also wants a separate block of the most notable events of the region that does not lean on personal tastes: an open-air concert, a fair, an open-doors day, and any seasonal event, such as the reenactment of the battle for Fort No. 5 around 9 May. The kinds of such events change through the year and cannot be listed in advance, so the pick must not depend on a fixed list of genres.

## Decision
- **Where it shows.** The Today screen of the Mini App and the Android app gets a "Топ рядом" block of up to 6 events. `GET /events/top` returns it; it is empty when the profile has no city or the listings have nothing.
- **What goes in.** Listings of the user's region for the next 14 days, one per title. The score is computed by code from what the listing itself says:
  - a public place in the venue or address (square, park, embankment, fort, stadium, beach and similar) +2;
  - free entry +1.5; a ticket above 3000 rubles -1;
  - a word of a mass event in the title (festival, fair, holiday, parade, open, marathon, night and similar) +2;
  - the same title on several dates +1 for each extra date, at most +2; a run of 4 hours or more +1;
  - the season +4 when the title or place carries a word of a holiday whose window covers today or starts within two weeks;
  - the user's own town +1, other towns lose up to 1.5 by distance.
- **Seasons.** A small table of holidays with a date window and keywords (New Year, 23 February, Maslenitsa, 8 March, Easter, 1-9 May, Russia Day, Navy Day, Day of Knowledge, Unity Day, Halloween). Movable holidays get a wide window. New rows are added in code; no schema or deploy of data is needed.
- **No tastes, no LLM.** The block ignores the check-in, goals and past choices, so every user in a region sees the same picks (the user's own town only breaks ties). The LLM does not take part.
- **Sources.** Still Timepad and KudaGo (ADR 0008). A search for open APIs or feeds of regional portals found none; a portal is added only through an official API or feed, or after the owner's decision on scraping.

## Consequences
The score is a heuristic and will mis-rank some events, for example a quiet lecture in a park. Seasonal keywords need an occasional review. If the listings have few mass events, the block shows what there is rather than nothing. A learned interest profile (the next step) stays separate: it feeds the assistant and the pool, while this block stays tastes-free on purpose so the user sees what the city is doing.
