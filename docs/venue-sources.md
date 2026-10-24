# Venue sources: bars, cafes and restaurants (issue #121)

English · [Русский](ru/venue-sources.md)

The M5 assistant ("Айда, организуй", #124) offers 3-5 places for a meetup. This note compares where the places can come from and what we can show about each. The choice is recorded in ADR 0011.

Research date: 2026-10-22. The cloud environment used for this research cannot reach Russian hosts (2GIS and Yandex documentation pages did not open), so the facts below come from search results and what the providers publish elsewhere, not from live calls or the official terms pages. Items that need a check against the official page are marked **verify**; the first run on the Russian VPS is the live check of the OpenStreetMap loader.

## What we need from a source

- Venues of the right kind (bar, pub, cafe, restaurant) near a city, in any Russian city (Ayda is not tied to one city).
- Free access, and terms that let us keep a snapshot of a venue inside a co-op quest and show it to the participants.
- Name, address, coordinates, and if possible opening hours, cuisine, a website. Reviews, a rating and an average bill are wanted but not required.
- No personal data leaves Ayda: a request carries a city or an area, never a user.
- Free only (project rule). No scraping.

## Candidates

| Source | Coverage | Fields | Terms and limits | Verdict |
|---|---|---|---|---|
| **OpenStreetMap** via Overpass API (tags `amenity=restaurant\|cafe\|bar\|pub\|fast_food`) | Every Russian city; dense in big cities, patchy in small towns and in the opening hours | name, address parts, coordinates, `cuisine`, `opening_hours`, `website`, `phone`, often `outdoor_seating`. **No reviews, rating or average bill** | ODbL: free for commercial use with the attribution "© OpenStreetMap contributors". Public Overpass instances are for light use: an app should make a few queries a day, identify itself with a User-Agent and not run parallel jobs; heavy or commercial use goes to a self-hosted instance. A monthly query per city fits the light use | **Use** as the base list |
| **2GIS** Places / Catalog API | Best Russian coverage, all cities | Rating and review count (seen in third-party scrapers' output); an average bill may exist for some venues (**verify**) | Free demo key with small quotas; a commercial agreement is needed for production and for storing data (**verify** on platform.2gis.ru) | **Do not depend on it** now; use as a link target. Revisit if the owner wants to pay |
| **Yandex Maps** organization search (Places) | Best Russian coverage | Rating, reviews, categories | The free terms ban storing or changing the data and allow display only on a Yandex map; the free Places quota is reported as 500 requests a day; storing needs the paid version (from the Yandex "terms of free use" page found by search, **verify**) | **Not usable**: we must store the picked venue in the quest |
| **Foursquare Places** | Weak in Russia | Rating, price tier 1-4 | Free credits then paid; terms reported to allow keeping only IDs; US service (**verify**) | Skip |
| **Google Places** | Good | Rating, price level | Paid, strict caching limits | Skip (free only) |
| Reviews sites (Tripadvisor, Zoon, Restoclub, Afisha) | Big cities | Reviews, average bill | No public free API; scraping breaks their terms and the database maker's right (Civil Code art. 1334) | Skip |
| **Our own reviews** | Only venues our users visit | Rating and a one-line note after a meetup | Ours, no licence problem | **Later**: after a meetup co-op closes, ask "how was it?" and show the average on the venue card |

## Recommendation

1. Base list from **OpenStreetMap**: a monthly Overpass query per city that has users (radius around the city center), stored in a `venues` table in the `events` module with the OSM id, name, kind, address, coordinates, `cuisine`, `opening_hours` and `website`. Code picks 3-5 candidates (kind, distance, opening hours at the planned time, a name that is not empty); the LLM only phrases the card.
2. For reviews and the average bill, each venue card carries **links to 2GIS and Yandex Maps** built from the venue name and city (search links, no API, no storage of their data): the user opens the venue there. The URL patterns are checked when the card is built in #124 (**verify**).
3. Show "© OpenStreetMap contributors" on the card (ODbL attribution) and send the app's name in the User-Agent of every Overpass request.
4. Later, collect our own ratings after meetups (a small follow-up, not part of M5's first cut).

## What this costs us

- Cards show no rating or average bill. The link to a maps app answers that in one tap, and the quest keeps working offline from the stored snapshot.
- OSM gaps in small towns: the assistant offers fewer than 3 places there and says so, or suggests an online session.
- Overpass can be slow or rate-limit us: the loader retries with backoff, tries a second public instance, and keeps the previous snapshot when both fail.
- OSM has opening hours but not a place closed for a while (renovation, "temporarily closed" on Yandex Maps). Cards say "открыто по графику", never just "open". Places the map itself marks as closed (`opening_hours=off|closed`, `disused:*`, `was:*` and similar lifecycle prefixes) are skipped on load. Every place card has a "Не работает" button: the place leaves that user's picks at once and everyone's once two people report it; a report lasts 30 days, then the place comes back (`events.venue_reports`, `POST /venues/{venue_id}/closed`).
