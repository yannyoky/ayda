"""Today's weather for a city center from Open-Meteo (free, no key)."""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_S = 3 * 3600
FROST_C = -15.0
STRONG_WIND_MS = 12.0
RAIN_PROBABILITY = 50

Condition = Literal["clear", "cloudy", "rain", "snow", "storm", "unknown"]


@dataclass(frozen=True)
class Weather:
    """Flags for quest selection over the rest of the local day."""

    temperature_c: float
    condition: Condition
    min_temp_c: float
    max_temp_c: float
    rain: bool
    frost: bool
    strong_wind: bool


def condition_for(code: int) -> Condition:
    """WMO weather interpretation code to a simple condition."""
    if code in (0, 1):
        return "clear"
    if code in (2, 3, 45, 48):
        return "cloudy"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    return "unknown"


def summarize(data: dict[str, Any], now_local: datetime) -> Weather:
    hourly = cast(dict[str, list[Any]], data["hourly"])
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    current_hour = now_local.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    idx = [
        i
        for i, t in enumerate(times)
        if t >= current_hour and t.date() == current_hour.date() and t.hour <= 22
    ] or [len(times) - 1]

    temps = [float(hourly["temperature_2m"][i]) for i in idx]
    codes = [int(hourly["weather_code"][i]) for i in idx]
    winds = [float(hourly["wind_speed_10m"][i]) for i in idx]
    probs = [int(hourly.get("precipitation_probability", [0] * len(times))[i] or 0) for i in idx]
    conditions: list[Condition] = [condition_for(c) for c in codes]

    wet = any(c in ("rain", "storm") for c in conditions) or max(probs) >= RAIN_PROBABILITY
    return Weather(
        temperature_c=round(temps[0], 1),
        condition=conditions[0],
        min_temp_c=min(temps),
        max_temp_c=max(temps),
        rain=wet,
        frost=min(temps) < FROST_C,
        strong_wind=max(winds) >= STRONG_WIND_MS,
    )


class WeatherClient:
    """Cached per city for 3 hours. Any failure gives None: the pool builds without weather."""

    def __init__(self, http: httpx.AsyncClient | None = None, url: str = OPEN_METEO_URL) -> None:
        self._http = http or httpx.AsyncClient(timeout=3.0)
        self._url = url
        self._cache: dict[int, tuple[float, dict[str, Any]]] = {}

    async def _fetch(self, lat: float, lon: float, tz: str) -> dict[str, Any]:
        response = await self._http.get(
            self._url,
            params={
                "latitude": round(lat, 2),
                "longitude": round(lon, 2),
                "hourly": "temperature_2m,weather_code,wind_speed_10m,precipitation_probability",
                "wind_speed_unit": "ms",
                "timezone": tz,
                "forecast_days": 2,
            },
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def today(
        self, city_id: int, lat: float, lon: float, tz: str, now: datetime | None = None
    ) -> Weather | None:
        cached = self._cache.get(city_id)
        try:
            if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
                data = cached[1]
            else:
                data = await self._fetch(lat, lon, tz)
                self._cache[city_id] = (time.monotonic(), data)
            return summarize(data, (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz)))
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError):
            return None

    async def aclose(self) -> None:
        await self._http.aclose()
