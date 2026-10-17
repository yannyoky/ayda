# 0008. Events from Timepad and KudaGo, PRO.Культура.РФ next

## Context
M3 (US-19) shows free and paid events in the user's city and region as quests in the daily pool. There is no single free events API that covers all of Russia. Ayda is not tied to one city, so a user in a small town must also get something from their region. The comparison of sources is in `docs/events-sources.md` (issue #38).

## Decision
- Events come only from documented APIs, never from scraping:
  - **Timepad** (`api.timepad.ru/v1/events`) for every city that has users and for the largest city of each region with users. Public events need no token; an optional `TIMEPAD_TOKEN` raises the rate limit.
  - **KudaGo** (`kudago.com/public-api/v1.4`) for the big cities it covers, mapped from our city reference by a fixed table of location slugs. No key.
  - **PRO.Культура.РФ** is the next source behind the same interface, switched on by `CULTURE_API_KEY` once the owner receives an integration key.
- Each source is a client behind one `EventSource` interface in the `events` module that returns normalized listings: source, source id, title, start, end, venue, address, coordinates, city, region, free flag, minimum price, link, category.
- A nightly worker job loads the next 3 days of events into `events.listings` (unique by source and source id), drops listings that ended more than 2 days ago, and logs only counts per source. A failing source does not stop the others.
- Requests to sources carry only a city name or slug and a time window; no user data leaves Ayda.
- An event quest shows the source name and a link to the source page.

## Consequences
Big cities get curated KudaGo events plus Timepad; other cities get Timepad events, which lean towards lectures, workshops and meetups, until PRO.Культура.РФ is connected. A new city starts getting events from the next nightly run. Duplicates between sources are possible and accepted in M3. Sources may change their API without notice; each client is small, tested against recorded responses, and a broken one only empties its share of listings.
