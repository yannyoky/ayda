# 0011. Venues from OpenStreetMap, reviews through map links

English · [Русский](../ru/decisions/0011-venues-from-osm.md)

## Context
The M5 meetup assistant (#124) needs bars, cafes and restaurants near the users, and the picked one is stored in a co-op quest (ADR 0010). Ayda uses free sources only, no scraping. The comparison is in `docs/venue-sources.md` (issue #121): 2GIS and Yandex have the reviews but their free terms do not allow keeping their data (Yandex bans it outright), and the other candidates are paid or not available in Russia.

## Decision
- Venues come from **OpenStreetMap** through the Overpass API: tags `amenity=restaurant|cafe|bar|pub|fast_food`, one query per city with users (radius around the city center), run monthly by the worker. Requests carry a city center and a radius only, and the app's name in the User-Agent. A failed load keeps the previous snapshot.
- They are stored in `events.venues` (OSM type and id, name, kind, cuisine, address, coordinates, opening hours, website, loaded at). The `events` module owns them; other modules get them through its interface, as with event listings.
- Code selects the 3-5 candidates (kind, distance, open at the planned time, has a name). The LLM only phrases the card; its output is validated against a JSON schema, as everywhere.
- A card carries "© OpenStreetMap contributors" and links to **2GIS** and **Yandex Maps** search for the venue's name and city, which is where the user reads reviews and sees the average bill. We do not call or store their data.
- The picked venue is copied as a snapshot into the co-op's `place` (ADR 0010), so the plan does not change when the venues table is refreshed.
- Later: our own ratings after meetups.

## Consequences
No rating or average bill on our cards, one tap away in a maps app. Small towns may have few venues; the assistant says so. Nothing is paid for and no key is needed; the load volume (dozens of queries a month) fits the public Overpass usage policy. If the owner later agrees to pay for 2GIS data, a new source goes behind the same interface without changing the cards' shape. The URL patterns of the map links and the real loading time of Overpass are checked during #124 and on the Russian VPS.
