# Events sources for Russian cities and regions (issue #38)

English · [Русский](ru/events-sources.md)

Ayda suggests local events (free and paid) as quests in the daily pool (US-19). There is no single free events API that covers all of Russia, so this note compares the candidates and recommends a set. The choice is recorded in ADR 0008.

Research date: 2026-10-17. The cloud environment used for this research cannot reach Russian hosts, so the facts below come from the providers' public documentation pages and search results, not from live calls. Each client is written against those docs and tested with recorded responses; the first nightly run on the Russian VPS is the live check.

## What we need from a source

- Coverage by city **and** by region (Ayda is not tied to one city).
- Free access, terms that allow showing events inside an app with a link back.
- Fields: title, start (and end) time, venue name and address, coordinates or at least a city, price or a free flag, a link to the source page.
- Daily updates are enough: listings refresh once a night (PRD, US-19).
- No personal data: only public events, nothing about our users goes to a source except a city name or slug.

## Candidates

| Source | Coverage | Access | Fields | Terms and limits | Verdict |
|---|---|---|---|---|---|
| **KudaGo** public API v1.4 (`kudago.com/public-api`) | About a dozen big cities: Moscow, Saint Petersburg, Novosibirsk, Yekaterinburg, Nizhny Novgorod, Kazan, Vyborg, Samara, Krasnodar, Sochi, Ufa, Krasnoyarsk. No regions, no small cities | Free, no key | title, dates (start, end as Unix time), place (title, address, coordinates), price as text, `is_free`, `site_url`, categories | Free database "for developers, webmasters and partners"; the docs ask for a link back to KudaGo. Editorial, curated, good quality | **Use** for the cities it covers |
| **Timepad** API v1 (`api.timepad.ru/v1/events`) | Any city: organizers all over Russia publish there. Many lectures, workshops, meetups, business and education events; fewer concerts and theatre | Public events can be read without a token (rate-limited); a free token from a Timepad account raises the limits | name, `starts_at`, `ends_at`, `location` (city, address, coordinates), ticket types with prices, categories, `url` | Public data, links back to Timepad event pages; filter by `cities`, start time and moderation status | **Use** for every city that has users |
| **PRO.Культура.РФ** (former AIS EIPSK, Ministry of Culture) export API | All regions, down to small towns: museums, libraries, theatres, houses of culture, many free events and Pushkin card events | Integration key on request (email `partners@team.culture.ru`); the same data as a weekly open-data dump at `opendata.mkrf.ru` (dataset "Мероприятия в сфере культуры") | event, places with coordinates, region (locale), dates, price, free flag, link to culture.ru | Official state data, open-data license for the dump; the open-data portal was reported unreliable for large downloads in 2025 | **Next source**, once the owner gets a key: best regional coverage |
| VK events (communities of type "event") | Everywhere, but uneven | User token; API for event search is limited and changes often | Free text, no reliable price or venue fields | VK terms forbid collecting data for third-party services without an agreement | Skip |
| Yandex Afisha, Afisha.ru, Kassir.ru, Ticketland | Big cities, mostly paid | No public API (partner programs only) | n/a | Scraping breaks their terms of use; listings are a protected database (Civil Code art. 1334, database maker's right) | Skip |
| Regional culture portals and city sites | One region each | Usually no API, sometimes RSS | Varies | Scraping is a legal and maintenance risk per site | Skip; PRO.Культура.РФ already aggregates most of them |

## Recommendation

1. **Timepad for every city that has users**, plus the largest city of each region with users, so a user in a small town still sees events in their region center.
2. **KudaGo for the big cities it covers**: better concerts, theatre and exhibitions than Timepad there.
3. **PRO.Культура.РФ as the third source** behind the same interface, enabled when the integration key is set (`CULTURE_API_KEY`). It fills small towns and regions with free cultural events. Getting the key needs a request from the owner.
4. No scraping. Only documented APIs and open data; each event shows its source and links to the source page.

Duplicates between sources (the same concert on KudaGo and Timepad) are rare enough to ignore in M3; a later dedupe can match on title, start time and venue distance.

## Legal notes on scraping

Where no API exists we do not scrape:
- Listings sites protect their collections as databases (Civil Code art. 1334) and forbid automated collection in their terms; copying them invites claims and IP blocks.
- Event descriptions and posters are copyrighted; we store only the facts we need (title, time, venue, price, link) and link to the source for the rest.
- Sources get no personal data: requests carry a city name or slug and a time window only.
