"""Events sources (ADR 0008): Timepad for any city, KudaGo for the big cities it covers.

Each client turns one source's API into normalized `ListingData`. Requests carry only a
city name or slug and a time window, never anything about our users.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import httpx

log = logging.getLogger(__name__)

TIMEPAD_URL = "https://api.timepad.ru/v1/events"
KUDAGO_URL = "https://kudago.com/public-api/v1.4/events/"
PAGE_SIZE = 100
MAX_PAGES = 5
DEFAULT_DURATION = timedelta(hours=2)


@dataclass(frozen=True)
class CityRef:
    """A city from our reference to load events for."""

    id: int
    name: str
    region_code: str


@dataclass(frozen=True)
class ListingData:
    source: str
    source_id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    venue: str | None
    address: str | None
    lat: float | None
    lon: float | None
    city_id: int
    region_code: str
    is_free: bool
    price_min: int | None
    url: str
    category: str


class EventSource(Protocol):
    name: str

    def supports(self, city: CityRef) -> bool: ...

    async def fetch(self, city: CityRef, since: datetime, until: datetime) -> list[ListingData]: ...


def clean_title(title: str) -> str:
    """KudaGo writes titles in lower case; make the first letter a capital."""
    title = " ".join(title.split())
    return title[:1].upper() + title[1:]


def _category(names: Sequence[str], default: str) -> str:
    joined = " ".join(n.lower() for n in names)
    rules = (
        ("sport", ("спорт", "sport", "yoga", "йог", "фитнес", "dance-training")),
        ("walk", ("экскурс", "tour", "прогул")),
        ("learning", ("образован", "education", "лекци", "lecture", "masterclass", "мастер-класс",
                      "наук", "бизнес", "business", "ит и", "язык", "психолог")),
        ("social", ("вечерин", "party", "игр", "games", "квест", "quest", "еда", "festival",
                    "фестивал", "social", "развлеч", "entertainment")),
        ("city", ("концерт", "concert", "театр", "theater", "выстав", "exhibition", "кино",
                  "cinema", "искусств", "art", "stand-up", "стендап", "музе")),
    )  # fmt: skip
    for category, hints in rules:
        if any(h in joined for h in hints):
            return category
    return default


def parse_time(value: str) -> datetime:
    """Timepad sends `2026-10-17T19:00:00+0300`; also accepts ISO with a colon offset."""
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_NUMBER = re.compile(r"\d[\d\s]*")


def price_from_text(text: str) -> int | None:
    """Lowest number in a price text such as "от 500 до 1 500 рублей"."""
    numbers = [int(m.replace(" ", "")) for m in _NUMBER.findall(text.replace("\xa0", " "))]
    return min(numbers) if numbers else None


def https_url(value: object) -> str:
    """A link from a listing, only if it is https: no javascript: or plain http (audit M5).
    A ValueError skips the event like any other malformed field."""
    url = str(value).strip()
    if not url.lower().startswith("https://") or any(c.isspace() for c in url):
        raise ValueError("not an https link")
    return url


# --- Timepad -----------------------------------------------------------------------------


class TimepadSource:
    """Public Timepad events by city name. A token is optional and only raises the limits."""

    name = "timepad"

    def __init__(
        self, http: httpx.AsyncClient, token: str | None = None, url: str = TIMEPAD_URL
    ) -> None:
        self._http = http
        self._token = token
        self._url = url

    def supports(self, city: CityRef) -> bool:
        return True

    async def fetch(self, city: CityRef, since: datetime, until: datetime) -> list[ListingData]:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        out: list[ListingData] = []
        for page in range(MAX_PAGES):
            response = await self._http.get(
                self._url,
                params={
                    "cities": city.name,
                    "starts_at_min": since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "starts_at_max": until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "moderation_statuses": "featured,shown",
                    "access_statuses": "public",
                    "fields": "location,ticket_types,ends_at,categories",
                    "sort": "+starts_at",
                    "limit": PAGE_SIZE,
                    "skip": page * PAGE_SIZE,
                },
                headers=headers,
            )
            response.raise_for_status()
            data = cast(dict[str, Any], response.json())
            values = cast(list[dict[str, Any]], data.get("values") or [])
            for item in values:
                listing = self._listing(item, city)
                if listing is not None:
                    out.append(listing)
            if len(values) < PAGE_SIZE:
                break
        return out

    def _listing(self, item: dict[str, Any], city: CityRef) -> ListingData | None:
        try:
            location = cast(dict[str, Any], item.get("location") or {})
            # Online events have no address; only places one can go to become quests.
            address = location.get("address")
            if not address or (location.get("city") or "").strip() != city.name:
                return None
            coords = cast(list[float] | None, location.get("coordinates"))
            prices = [
                int(t["price"])
                for t in cast(list[dict[str, Any]], item.get("ticket_types") or [])
                if t.get("price") is not None
            ]
            is_free = bool(prices) and max(prices) == 0
            paid = [p for p in prices if p > 0]
            categories = cast(list[dict[str, Any]], item.get("categories") or [])
            return ListingData(
                source=self.name,
                source_id=str(item["id"]),
                title=clean_title(str(item["name"])),
                starts_at=parse_time(str(item["starts_at"])),
                ends_at=parse_time(str(item["ends_at"])) if item.get("ends_at") else None,
                venue=None,
                address=str(address),
                lat=float(coords[0]) if coords and len(coords) == 2 else None,
                lon=float(coords[1]) if coords and len(coords) == 2 else None,
                city_id=city.id,
                region_code=city.region_code,
                is_free=is_free,
                price_min=None if is_free or not paid else min(paid),
                url=https_url(item["url"]),
                category=_category([str(c.get("name", "")) for c in categories], "learning"),
            )
        except (KeyError, TypeError, ValueError):
            log.warning("timepad: skipped a malformed event")
            return None


# --- KudaGo ------------------------------------------------------------------------------

# Our city reference name -> KudaGo location slug.
KUDAGO_LOCATIONS = {
    "Москва": "msk",
    "Санкт-Петербург": "spb",
    "Новосибирск": "nsk",
    "Екатеринбург": "ekb",
    "Нижний Новгород": "nnv",
    "Казань": "kzn",
    "Выборг": "vbg",
    "Самара": "smr",
    "Краснодар": "krd",
    "Сочи": "sochi",
    "Уфа": "ufa",
    "Красноярск": "krasnoyarsk",
}


class KudaGoSource:
    """Curated KudaGo events for the cities it covers; no key."""

    name = "kudago"

    def __init__(self, http: httpx.AsyncClient, url: str = KUDAGO_URL) -> None:
        self._http = http
        self._url = url

    def supports(self, city: CityRef) -> bool:
        return city.name in KUDAGO_LOCATIONS

    async def fetch(self, city: CityRef, since: datetime, until: datetime) -> list[ListingData]:
        out: list[ListingData] = []
        url: str | None = self._url
        params: dict[str, str | int] | None = {
            "lang": "ru",
            "location": KUDAGO_LOCATIONS[city.name],
            "actual_since": int(since.timestamp()),
            "actual_until": int(until.timestamp()),
            "fields": "id,title,dates,place,price,is_free,site_url,categories",
            "expand": "place",
            "text_format": "text",
            "page_size": PAGE_SIZE,
        }
        for _ in range(MAX_PAGES):
            if url is None:
                break
            response = await self._http.get(url, params=params)
            response.raise_for_status()
            data = cast(dict[str, Any], response.json())
            for item in cast(list[dict[str, Any]], data.get("results") or []):
                out.extend(self._listings(item, city, since, until))
            url = cast(str | None, data.get("next"))
            params = None  # `next` already carries the query
        return out

    def _listings(
        self, item: dict[str, Any], city: CityRef, since: datetime, until: datetime
    ) -> list[ListingData]:
        """One listing per date of the event inside the window."""
        try:
            place = cast(dict[str, Any] | None, item.get("place"))
            if not place:
                return []
            coords = cast(dict[str, Any], place.get("coords") or {})
            is_free = bool(item.get("is_free"))
            price = None if is_free else price_from_text(str(item.get("price") or ""))
            template = ListingData(
                source=self.name,
                source_id=str(item["id"]),
                title=clean_title(str(item["title"])),
                starts_at=since,
                ends_at=None,
                venue=clean_title(str(place["title"])) if place.get("title") else None,
                address=place.get("address") or None,
                lat=float(coords["lat"]) if coords.get("lat") is not None else None,
                lon=float(coords["lon"]) if coords.get("lon") is not None else None,
                city_id=city.id,
                region_code=city.region_code,
                is_free=is_free,
                price_min=price,
                url=https_url(item["site_url"]),
                category=_category(cast(list[str], item.get("categories") or []), "city"),
            )
            out: list[ListingData] = []
            for d in cast(list[dict[str, Any]], item.get("dates") or []):
                start_ts, end_ts = d.get("start"), d.get("end")
                if not isinstance(start_ts, int | float):
                    continue
                starts = datetime.fromtimestamp(start_ts, UTC)
                if not since <= starts <= until:
                    continue  # also drops KudaGo's "always open" placeholder dates
                ends = (
                    datetime.fromtimestamp(end_ts, UTC)
                    if isinstance(end_ts, int | float) and end_ts > start_ts
                    else None
                )
                out.append(
                    replace(
                        template,
                        source_id=f"{item['id']}:{int(start_ts)}",
                        starts_at=starts,
                        ends_at=ends,
                    )
                )
            return out
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            log.warning("kudago: skipped a malformed event")
            return []
