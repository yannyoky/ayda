"""Venues for meetups from OpenStreetMap (ADR 0011): a monthly Overpass query per city with
users, stored in `events.venues`, and code that picks 3-5 candidates. Since M6 (ADR 0013) the
same query also loads places for a walk: parks, gardens, embankments, viewpoints and squares.

Requests carry a city center and a radius only, never anything about our users. Reviews and
the average bill are not stored: a card links to 2GIS and Yandex Maps search instead.
"""

import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, cast
from urllib.parse import quote

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.events.cities import city_point
from ayda.modules.events.models import Venue, VenueLoad, VenueReport

log = logging.getLogger(__name__)

FOOD_KINDS = ("restaurant", "cafe", "bar", "pub", "fast_food")
WALK_KINDS = ("park", "garden", "embankment", "viewpoint", "square")
KINDS = FOOD_KINDS + WALK_KINDS
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RELOAD_AFTER = timedelta(days=30)
ATTRIBUTION = "© OpenStreetMap contributors"
MAX_NAME = 120
MAX_VENUES_PER_CITY = 3000
# "Не работает" from users: the map knows opening hours, not that a place shut for a while.
REPORT_TTL = timedelta(days=30)
REPORTS_TO_HIDE = 2
# OSM lifecycle prefixes for a place that no longer works (`disused:amenity=bar`).
_GONE_PREFIXES = ("disused:", "abandoned:", "was:", "demolished:", "razed:", "removed:")


@dataclass(frozen=True)
class VenueData:
    osm_type: str
    osm_id: int
    name: str
    kind: str
    lat: float
    lon: float
    cuisine: str | None = None
    address: str | None = None
    opening_hours: str | None = None
    website: str | None = None


def query_for(lat: float, lon: float, radius_m: int) -> str:
    around = f"(around:{radius_m},{lat:.5f},{lon:.5f})"
    return (
        f"[out:json][timeout:90];("
        f'nwr["amenity"~"^({"|".join(FOOD_KINDS)})$"]["name"]{around};'
        f'nwr["leisure"~"^(park|garden)$"]["name"]{around};'
        f'nwr["tourism"="viewpoint"]["name"]{around};'
        f'nwr["place"="square"]["name"]{around};'
        f'way["highway"]["name"~"набережная",i]{around};'
        f");out center tags {MAX_VENUES_PER_CITY};"
    )


def _kind(tags: dict[str, str]) -> str | None:
    amenity = tags.get("amenity")
    if amenity in FOOD_KINDS:
        return amenity
    if tags.get("leisure") in ("park", "garden"):
        return tags["leisure"]
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    if tags.get("place") == "square":
        return "square"
    if "highway" in tags and "набережная" in tags.get("name", "").lower():
        return "embankment"
    return None


def is_closed(tags: dict[str, str]) -> bool:
    """A place the map itself marks as closed: hours `off`/`closed` or a lifecycle prefix."""
    if tags.get("opening_hours", "").strip().lower() in ("off", "closed"):
        return True
    return any(key.startswith(_GONE_PREFIXES) for key in tags)


def parse_venues(payload: dict[str, Any]) -> list[VenueData]:
    """Named places of the known kinds with coordinates; anything else, and a place the map
    marks as closed, is skipped. An embankment split into several ways is kept once, by name."""
    out: list[VenueData] = []
    embankments: set[str] = set()
    for element in cast(list[dict[str, Any]], payload.get("elements", [])):
        tags = cast(dict[str, str], element.get("tags") or {})
        center = cast(dict[str, float], element.get("center") or {})
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        name = " ".join(tags.get("name", "").split())
        kind = _kind(tags)
        osm_type = element.get("type")
        if (
            not name
            or kind not in KINDS
            or lat is None
            or lon is None
            or osm_type not in ("node", "way", "relation")
            or is_closed(tags)
        ):
            continue
        if kind == "embankment":
            if name.lower() in embankments:
                continue
            embankments.add(name.lower())
        street = tags.get("addr:street")
        number = tags.get("addr:housenumber")
        address = ", ".join(p for p in (street, number) if p) or None
        website = tags.get("website") or tags.get("contact:website")
        out.append(
            VenueData(
                osm_type=osm_type,
                osm_id=int(element["id"]),
                name=name[:MAX_NAME],
                kind=kind,
                lat=float(lat),
                lon=float(lon),
                cuisine=tags.get("cuisine"),
                address=address,
                opening_hours=tags.get("opening_hours"),
                website=website if website and website.startswith("https://") else None,
            )
        )
    return out


class OverpassSource:
    """Public Overpass instances in order; the next one is tried when one fails."""

    def __init__(self, http: httpx.AsyncClient, urls: Sequence[str] = (OVERPASS_URL,)) -> None:
        self._http = http
        self._urls = list(urls)

    async def fetch(self, lat: float, lon: float, radius_m: int) -> list[VenueData]:
        last: Exception | None = None
        for url in self._urls:
            try:
                response = await self._http.post(url, data={"data": query_for(lat, lon, radius_m)})
                response.raise_for_status()
                return parse_venues(response.json())
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                log.warning("venues: %s failed: %s", httpx.URL(url).host, type(exc).__name__)
        raise last or httpx.HTTPError("no Overpass instance configured")


# --- storing -----------------------------------------------------------------------------

_UPSERT = text(
    """
    INSERT INTO events.venues (
        osm_type, osm_id, city_id, name, kind, cuisine, address, location,
        opening_hours, website, loaded_at
    ) VALUES (
        :osm_type, :osm_id, :city_id, :name, :kind, :cuisine, :address,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
        :opening_hours, :website, :loaded_at
    )
    ON CONFLICT (osm_type, osm_id) DO UPDATE SET
        city_id = EXCLUDED.city_id, name = EXCLUDED.name, kind = EXCLUDED.kind,
        cuisine = EXCLUDED.cuisine, address = EXCLUDED.address, location = EXCLUDED.location,
        opening_hours = EXCLUDED.opening_hours, website = EXCLUDED.website,
        loaded_at = EXCLUDED.loaded_at
    """
)


async def save_venues(
    session: AsyncSession, city_id: int, items: Sequence[VenueData], now: datetime
) -> int:
    """Replace a city's snapshot with a successful load: refresh what came back, drop what
    did not, and remember when it was loaded."""
    unique = {(v.osm_type, v.osm_id): v for v in items}
    if unique:
        await session.execute(
            _UPSERT,
            [
                {
                    "osm_type": v.osm_type,
                    "osm_id": v.osm_id,
                    "city_id": city_id,
                    "name": v.name,
                    "kind": v.kind,
                    "cuisine": v.cuisine,
                    "address": v.address,
                    "lat": v.lat,
                    "lon": v.lon,
                    "opening_hours": v.opening_hours,
                    "website": v.website,
                    "loaded_at": now,
                }
                for v in unique.values()
            ],
        )
    await session.execute(delete(Venue).where(Venue.city_id == city_id, Venue.loaded_at < now))
    await session.execute(
        text(
            "INSERT INTO events.venue_loads (city_id, loaded_at, venues)"
            " VALUES (:city_id, :now, :n)"
            " ON CONFLICT (city_id) DO UPDATE SET loaded_at = :now, venues = :n"
        ),
        {"city_id": city_id, "now": now, "n": len(unique)},
    )
    return len(unique)


async def is_loaded(session: AsyncSession, city_id: int) -> bool:
    """Whether the city's venues were ever loaded (a load of an empty map still counts)."""
    return await session.get(VenueLoad, city_id) is not None


async def cities_due(
    session: AsyncSession, city_ids: Sequence[int], now: datetime, limit: int
) -> list[int]:
    """Cities never loaded or loaded over 30 days ago, never-loaded first."""
    if not city_ids:
        return []
    loaded = {
        r.city_id: r.loaded_at
        for r in await session.scalars(select(VenueLoad).where(VenueLoad.city_id.in_(city_ids)))
    }
    due = [i for i in sorted(set(city_ids)) if i not in loaded or now - loaded[i] >= RELOAD_AFTER]
    due.sort(key=lambda i: loaded.get(i, datetime.min.replace(tzinfo=now.tzinfo)))
    return due[:limit]


async def load_venues(
    session: AsyncSession,
    source: OverpassSource,
    city_ids: Sequence[int],
    radius_m: int,
    now: datetime,
    limit: int = 10,
) -> dict[int, int]:
    """Load the cities that are due, a few per run to stay within the light use of the public
    instances. A failed city keeps its previous snapshot and is tried again next run. Old
    "Не работает" reports are forgotten on the same run."""
    await purge_reports(session, now)
    loaded: dict[int, int] = {}
    for city_id in await cities_due(session, city_ids, now, limit):
        point = await city_point(session, city_id)
        if point is None:
            continue
        try:
            items = await source.fetch(point.lat, point.lon, radius_m)
        except (httpx.HTTPError, ValueError):
            continue
        loaded[city_id] = await save_venues(session, city_id, items, now)
    log.info("venues: loaded %d cities, %d venues", len(loaded), sum(loaded.values()))
    return loaded


# --- opening hours -----------------------------------------------------------------------

_WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
_TIMES = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _days(spec: str) -> set[int] | None:
    out: set[int] = set()
    for part in spec.split(","):
        bounds = part.strip().split("-")
        if not all(b in _WEEKDAYS for b in bounds) or len(bounds) > 2:
            return None
        first = _WEEKDAYS.index(bounds[0])
        last = _WEEKDAYS.index(bounds[-1])
        out.update(
            range(first, last + 1) if first <= last else [*range(first, 7), *range(last + 1)]
        )
    return out


def _intervals(spec: str) -> list[tuple[int, int]] | None:
    """Minutes of the day; an end past midnight is counted beyond 1440."""
    out: list[tuple[int, int]] = []
    for part in spec.split(","):
        m = _TIMES.match(part.strip())
        if m is None:
            return None
        start = int(m[1]) * 60 + int(m[2])
        end = int(m[3]) * 60 + int(m[4])
        if end <= start:
            end += 1440
        out.append((start, end))
    return out


def is_open_at(opening_hours: str | None, when: datetime) -> bool | None:
    """Whether a venue is open at a local time; None if unknown or not in the simple forms
    (`24/7`, `Mo-Fr 09:00-18:00; Sa,Su 10:00-16:00`, `off`)."""
    if not opening_hours:
        return None
    rules = [r.strip() for r in opening_hours.split(";") if r.strip()]
    per_day: dict[int, list[tuple[int, int]]] = {d: [] for d in range(7)}
    for rule in rules:
        if rule == "24/7":
            for d in range(7):
                per_day[d] = [(0, 1440)]
            continue
        head, _, tail = rule.rpartition(" ")
        days = _days(head) if head and head[0].isalpha() else set(range(7))
        times = None if tail.lower() == "off" else _intervals(tail if head else rule)
        if days is None or (times is None and tail.lower() != "off"):
            return None
        for d in days:
            per_day[d] = times or []
    minute = when.hour * 60 + when.minute
    today = when.weekday()
    if any(start <= minute < end for start, end in per_day[today]):
        return True
    yesterday = per_day[(today - 1) % 7]
    return any(end > 1440 and minute < end - 1440 for _, end in yesterday)


# --- candidates and links ----------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    venue: Venue
    lat: float
    lon: float
    distance_m: int
    open_now: bool | None


async def candidates(
    session: AsyncSession,
    city_id: int,
    when_local: datetime,
    kinds: Sequence[str] = FOOD_KINDS,
    limit: int = 5,
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
    only_ids: Sequence[int] | None = None,
) -> list[Candidate]:
    """Up to `limit` venues near the city center: open at the planned time first (unknown
    hours do not disqualify), then those with an address, then the closest. A place the user
    reported as not working is left out for them, and for everyone once enough people did.
    `only_ids` limits the search to those venues of any kind."""
    wanted = [k for k in kinds if k in KINDS]
    if only_ids is not None:
        wanted = list(KINDS)
    if not wanted or (only_ids is not None and not only_ids):
        return []
    since = (now or datetime.now(UTC)) - REPORT_TTL
    rows = (
        await session.execute(
            text(
                """
                SELECT v.id, ST_Y(v.location::geometry), ST_X(v.location::geometry),
                       ST_Distance(v.location, c.location)::int
                FROM events.venues v JOIN events.cities c ON c.id = v.city_id
                WHERE v.city_id = :city_id AND v.kind = ANY(:kinds)
                  AND (CAST(:ids AS bigint[]) IS NULL OR v.id = ANY(CAST(:ids AS bigint[])))
                  AND NOT EXISTS (
                      SELECT 1 FROM events.venue_reports r
                      WHERE r.venue_id = v.id AND r.reported_at >= :since
                      HAVING count(*) >= :to_hide
                          OR bool_or(r.user_id = CAST(:user_id AS uuid))
                  )
                ORDER BY ST_Distance(v.location, c.location), v.id
                LIMIT 200
                """
            ),
            {
                "city_id": city_id,
                "kinds": wanted,
                "since": since,
                "to_hide": REPORTS_TO_HIDE,
                "user_id": user_id,
                "ids": list(only_ids) if only_ids is not None else None,
            },
        )
    ).all()
    by_id = {
        v.id: v
        for v in await session.scalars(select(Venue).where(Venue.id.in_([r[0] for r in rows])))
    }
    found: list[Candidate] = []
    for venue_id, lat, lon, distance in rows:
        venue = by_id[venue_id]
        state = is_open_at(venue.opening_hours, when_local)
        if state is False and only_ids is None:
            continue
        found.append(Candidate(venue, float(lat), float(lon), int(distance), state))
    found.sort(key=lambda c: (c.open_now is not True, c.venue.address is None, c.distance_m))
    return found[:limit]


_LATIN = {
    "shch": "щ", "sch": "щ", "sh": "ш", "ch": "ч", "zh": "ж", "kh": "х", "ts": "ц", "ya": "я",
    "yu": "ю", "yo": "е", "oo": "у", "ee": "и", "ph": "ф", "ck": "к", "a": "а", "b": "б",
    "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х", "i": "и", "j": "ж", "k": "к",
    "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т",
    "u": "у", "v": "в", "w": "в", "x": "кс", "y": "и", "z": "з",
}  # fmt: skip
_LATIN_RE = re.compile("|".join(sorted(_LATIN, key=len, reverse=True)))
NAME_MATCH = 0.78


def normalize_name(name: str) -> str:
    """A place name for comparing: lower case, Latin letters read as Russian ones, no spaces,
    quotes or double letters, so «Rosterhit», «Ростерхит» and «ростер хит» are close."""
    lowered = name.lower().replace("ё", "е")
    cyrillic = _LATIN_RE.sub(lambda m: _LATIN[m[0]], lowered)
    letters = "".join(ch for ch in cyrillic if ch.isalnum())
    return re.sub(r"(.)\1+", r"\1", letters).replace("оа", "о")


def name_score(wanted: str, venue_name: str) -> float:
    a, b = normalize_name(wanted), normalize_name(venue_name)
    if not a or not b:
        return 0.0
    if len(a) >= 4 and (a in b or b in a):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


async def find_named(
    session: AsyncSession,
    city_id: int,
    wanted: str,
    when_local: datetime,
    limit: int = 3,
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> list[Candidate]:
    """Venues of the city whose name is what the chat named, best match first. A place
    named in the chat is never dropped for being closed: the friends know where they go, and
    the card still shows the hours."""
    rows = (
        await session.execute(select(Venue.id, Venue.name).where(Venue.city_id == city_id))
    ).all()
    scored = sorted(((name_score(wanted, name), venue_id) for venue_id, name in rows), reverse=True)
    ids = [venue_id for score, venue_id in scored if score >= NAME_MATCH][:limit]
    if not ids:
        return []
    found = await candidates(
        session, city_id, when_local, KINDS, len(ids), user_id, now, only_ids=ids
    )
    order = {venue_id: i for i, venue_id in enumerate(ids)}
    return sorted(found, key=lambda c: order[c.venue.id])


async def report_closed(
    session: AsyncSession, venue_id: int, user_id: uuid.UUID, now: datetime
) -> bool:
    """The user says the place does not work; False if there is no such venue. A repeated
    report refreshes its date, so one person never counts twice."""
    if await session.get(Venue, venue_id) is None:
        return False
    await session.execute(
        text(
            "INSERT INTO events.venue_reports (venue_id, user_id, reported_at)"
            " VALUES (:venue_id, :user_id, :now)"
            " ON CONFLICT (venue_id, user_id) DO UPDATE SET reported_at = :now"
        ),
        {"venue_id": venue_id, "user_id": user_id, "now": now},
    )
    return True


async def purge_reports(session: AsyncSession, now: datetime) -> int:
    """Forget reports past their 30 days: the place may have opened again."""
    result = await session.execute(
        delete(VenueReport).where(VenueReport.reported_at < now - REPORT_TTL)
    )
    return cast(Any, result).rowcount or 0


def map_links(name: str, city_name: str) -> dict[str, str]:
    """Search links where the user reads reviews and the average bill; nothing of theirs is
    called or stored."""
    query = quote(f"{name} {city_name}")
    return {
        "2gis": f"https://2gis.ru/search/{query}",
        "yandex": f"https://yandex.ru/maps/?text={query}",
    }


def osm_url(venue: Venue) -> str:
    return f"https://www.openstreetmap.org/{venue.osm_type}/{venue.osm_id}"


def _snapshot(venue: Venue, lat: float, lon: float) -> dict[str, Any]:
    return {
        "name": venue.name,
        "address": venue.address,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "link": osm_url(venue),
        "source": "osm",
        "source_id": f"{venue.osm_type}/{venue.osm_id}",
    }


def place_snapshot(candidate: Candidate) -> dict[str, Any]:
    """The venue as stored in a co-op's `place` (ADR 0010)."""
    return _snapshot(candidate.venue, candidate.lat, candidate.lon)


async def venue_place(session: AsyncSession, venue_id: int) -> tuple[Venue, dict[str, Any]] | None:
    """A venue by id with its place snapshot, or None."""
    venue = await session.get(Venue, venue_id)
    if venue is None:
        return None
    row = (
        await session.execute(
            text(
                "SELECT ST_Y(location::geometry), ST_X(location::geometry)"
                " FROM events.venues WHERE id = :id"
            ),
            {"id": venue_id},
        )
    ).one()
    return venue, _snapshot(venue, float(row[0]), float(row[1]))
