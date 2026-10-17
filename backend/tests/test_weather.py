from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ayda.modules.events import WeatherClient

TZ = "Europe/Kaliningrad"


def forecast(temp: float = 10, code: int = 1, wind: float = 3, prob: int = 0) -> dict[str, Any]:
    times = [f"2026-10-16T{h:02d}:00" for h in range(24)] + [
        f"2026-10-17T{h:02d}:00" for h in range(24)
    ]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [temp] * 48,
            "weather_code": [code] * 48,
            "wind_speed_10m": [wind] * 48,
            "precipitation_probability": [prob] * 48,
        }
    }


def client_for(payload: dict[str, Any] | None, calls: list[httpx.Request]) -> WeatherClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if payload is None:
            return httpx.Response(503)
        return httpx.Response(200, json=payload)

    return WeatherClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


NOW = datetime(2026, 10, 16, 9, 0, tzinfo=ZoneInfo(TZ))


async def test_clear_day() -> None:
    calls: list[httpx.Request] = []
    weather = await client_for(forecast(), calls).today(435, 54.7, 20.5, TZ, NOW)

    assert weather is not None
    assert weather.condition == "clear"
    assert (weather.rain, weather.frost, weather.strong_wind) == (False, False, False)
    assert calls[0].url.params["timezone"] == TZ


async def test_rain_frost_and_wind_flags() -> None:
    calls: list[httpx.Request] = []
    rainy = await client_for(forecast(code=63), calls).today(1, 0, 0, TZ, NOW)
    likely = await client_for(forecast(prob=70), calls).today(2, 0, 0, TZ, NOW)
    frosty = await client_for(forecast(temp=-20, code=71), calls).today(3, 0, 0, TZ, NOW)
    windy = await client_for(forecast(wind=15), calls).today(4, 0, 0, TZ, NOW)

    assert rainy and rainy.rain and rainy.condition == "rain"
    assert likely and likely.rain
    assert frosty and frosty.frost and frosty.condition == "snow" and not frosty.rain
    assert windy and windy.strong_wind
    assert rainy and not rainy.storm


async def test_storm_later_today() -> None:
    payload = forecast()
    payload["hourly"]["weather_code"][15] = 95  # 15:00 local, later than NOW

    weather = await client_for(payload, []).today(5, 0, 0, TZ, NOW)

    assert weather and weather.condition == "clear"
    assert weather.storm and weather.rain


async def test_cached_per_city() -> None:
    calls: list[httpx.Request] = []
    client = client_for(forecast(), calls)

    await client.today(435, 54.7, 20.5, TZ, NOW)
    await client.today(435, 54.7, 20.5, TZ, NOW)
    await client.today(1, 44.6, 40.1, "Europe/Moscow", NOW)

    assert len(calls) == 2


async def test_failure_means_unknown_weather() -> None:
    calls: list[httpx.Request] = []
    assert await client_for(None, calls).today(435, 54.7, 20.5, TZ, NOW) is None
    assert await client_for({"bad": 1}, calls).today(436, 54.7, 20.5, TZ, NOW) is None
