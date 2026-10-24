"""Live checks of the external services the app depends on: `python -m ayda.smoke`.

Each check calls the real service through the app's own client with the current settings and
prints one line: ok, fail or skip (not configured). Run it where the app runs, because what a
server can reach differs by country (Groq answers 403 to Russian IPs):

    docker compose -f docker-compose.prod.yml exec api python -m ayda.smoke

The same checks run as `pytest -m live` (tests/live). Output never carries keys, tokens or
response bodies, only the service, the outcome and a short reason.
"""

import asyncio
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from pydantic import SecretStr

from ayda.app import events as local_events
from ayda.core.config import Settings, get_settings
from ayda.core.storage import Storage
from ayda.modules import assistant, events
from ayda.modules.assistant.providers import extract_json

Status = Literal["ok", "fail", "skip"]

# Central Moscow: every source covers it, so an empty answer means the source is broken.
MOSCOW = events.CityRef(id=0, name="Москва", region_code="77")
MOSCOW_LAT, MOSCOW_LON, MOSCOW_TZ = 55.7558, 37.6173, "Europe/Moscow"
VENUE_RADIUS_M = 400
LLM_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class Result:
    name: str
    status: Status
    detail: str
    ms: int = 0


class Skip(Exception):
    """The service is not configured here."""


Probe = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class Check:
    name: str
    probe: Probe


async def run_check(check: Check) -> Result:
    started = time.monotonic()
    try:
        detail = await check.probe()
        status: Status = "ok"
    except Skip as exc:
        return Result(check.name, "skip", str(exc))
    except Exception as exc:  # a smoke check reports every failure
        # Only the type and our own messages: httpx errors can quote URLs with tokens in them.
        detail = str(exc) if isinstance(exc, (AssertionError, assistant.ProviderError)) else ""
        detail = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
        status = "fail"
    return Result(check.name, status, detail, int((time.monotonic() - started) * 1000))


def _secret(value: SecretStr | None) -> str:
    """An empty variable (e.g. a missing CI secret) counts as not set."""
    return value.get_secret_value() if value is not None else ""


def _window() -> tuple[datetime, datetime]:
    since = datetime.now(UTC)
    return since, since + timedelta(days=3)


async def _weather() -> str:
    client = events.WeatherClient(httpx.AsyncClient(timeout=10.0))
    try:
        weather = await client.today(0, MOSCOW_LAT, MOSCOW_LON, MOSCOW_TZ)
    finally:
        await client.aclose()
    assert weather is not None, "no forecast"
    return f"{weather.temperature_c:+.0f}°C, {weather.condition}"


def _source_check(name: str, settings: Settings) -> Check:
    async def probe() -> str:
        async with local_events.source_http() as http:
            sources = {s.name: s for s in local_events.default_sources(settings, http)}
            source = sources.get(name)
            if source is None:
                raise Skip("not in EVENTS_SOURCES")
            listings = await source.fetch(MOSCOW, *_window())
        assert listings, "no events in Moscow for 3 days"
        broken = [x for x in listings if not x.title or not x.url.startswith("http")]
        assert not broken, f"{len(broken)} listings without a title or link"
        return f"{len(listings)} events in Moscow"

    return Check(f"events:{name}", probe)


def _overpass_check(url: str) -> Check:
    async def probe() -> str:
        async with local_events.venue_http() as http:
            source = events.OverpassSource(http, [url])
            venues = await source.fetch(MOSCOW_LAT, MOSCOW_LON, VENUE_RADIUS_M)
        assert venues, "no places around central Moscow"
        return f"{len(venues)} places"

    return Check(f"venues:{httpx.URL(url).host}", probe)


def _llm_check(provider: assistant.LLMProvider) -> Check:
    async def probe() -> str:
        answer = await provider.complete(
            'Answer with a JSON object only, exactly {"ok": true}.',
            "Health check.",
            LLM_TIMEOUT_S,
        )
        assert extract_json(answer) == {"ok": True}, "unexpected answer"
        return provider.model

    return Check(f"llm:{provider.name}", probe)


def _telegram_check(settings: Settings) -> Check:
    async def probe() -> str:
        token = _secret(settings.telegram_bot_token)
        if not token:
            raise Skip("TELEGRAM_BOT_TOKEN not set")
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(f"https://api.telegram.org/bot{token}/getMe")
        assert response.status_code == 200, f"HTTP {response.status_code}"
        return "@" + str(response.json()["result"]["username"])

    return Check("telegram", probe)


def _s3_check(settings: Settings) -> Check:
    async def probe() -> str:
        if not _secret(settings.s3_access_key_id) or not _secret(settings.s3_secret_access_key):
            raise Skip("S3 keys not set")
        await Storage(settings).list_keys("smoke/")
        return f"bucket {settings.s3_bucket}"

    return Check("s3", probe)


def checks(settings: Settings, http: httpx.AsyncClient) -> list[Check]:
    out = [Check("weather", _weather)]
    out += [_source_check(name, settings) for name in ("timepad", "kudago")]
    urls = [u.strip() for u in settings.venues_overpass_urls.split(",") if u.strip()]
    out += [_overpass_check(url) for url in urls]
    llms = assistant.providers_from_settings(settings, http)
    out += [_llm_check(p) for p in llms] or [Check("llm", _no_llm)]
    out += [_telegram_check(settings), _s3_check(settings)]
    return out


async def _no_llm() -> str:
    raise Skip("no provider in LLM_PROVIDERS has a key")


async def main(settings: Settings) -> int:
    async with httpx.AsyncClient() as http:
        results = [await run_check(c) for c in checks(settings, http)]
    for r in results:
        timing = f" ({r.ms} ms)" if r.status != "skip" else ""
        print(f"{r.status.upper():4}  {r.name:32} {r.detail}{timing}")
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(get_settings())))
