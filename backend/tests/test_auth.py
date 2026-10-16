import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ayda.modules.auth import InitDataError, validate_init_data
from tests.contract import assert_matches
from tests.helpers import TEST_BOT_TOKEN, make_init_data, sign_in


def test_valid_init_data_is_parsed() -> None:
    raw = make_init_data(42, "Аня", start_param="invite123", photo_url="https://t.me/i/a.jpg")

    data = validate_init_data(raw, TEST_BOT_TOKEN)

    assert data.user.id == 42
    assert data.user.first_name == "Аня"
    assert data.user.photo_url == "https://t.me/i/a.jpg"
    assert data.start_param == "invite123"


def test_forged_init_data_is_rejected() -> None:
    raw = make_init_data(42, bot_token="999:OTHER")
    with pytest.raises(InitDataError):
        validate_init_data(raw, TEST_BOT_TOKEN)


def test_tampered_user_is_rejected() -> None:
    raw = make_init_data(42).replace("42", "43")
    with pytest.raises(InitDataError):
        validate_init_data(raw, TEST_BOT_TOKEN)


def test_init_data_older_than_24h_is_rejected() -> None:
    old = int((datetime.now(UTC) - timedelta(hours=24, minutes=1)).timestamp())
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(make_init_data(auth_date=old), TEST_BOT_TOKEN)


def test_init_data_just_under_24h_is_accepted() -> None:
    recent = int(time.time()) - 23 * 3600
    assert validate_init_data(make_init_data(auth_date=recent), TEST_BOT_TOKEN).user.id == 1001


@pytest.mark.parametrize("raw", ["", "garbage", "hash=abc", "a=1&a=2&hash=x"])
def test_malformed_init_data_is_rejected(raw: str) -> None:
    with pytest.raises(InitDataError):
        validate_init_data(raw, TEST_BOT_TOKEN)


async def test_first_sign_in_creates_user_and_later_finds_it(client: httpx.AsyncClient) -> None:
    first = await client.post("/auth/telegram", json={"init_data": make_init_data(7, "Саша")})
    assert first.status_code == 200
    assert_matches(first, "signInWithTelegram")
    body = first.json()
    assert body["user"]["first_name"] == "Саша"
    assert body["user"]["onboarded"] is False
    assert body["user"]["consent_required"] == "2026-10-16"
    assert body["user"]["theme"] == "graphite"

    second = await client.post("/auth/telegram", json={"init_data": make_init_data(7, "Саня")})
    assert second.json()["user"]["id"] == body["user"]["id"]
    assert second.json()["user"]["first_name"] == "Саня"


async def test_forged_sign_in_returns_401_problem(client: httpx.AsyncClient) -> None:
    raw = make_init_data(7, bot_token="1:FORGED")
    response = await client.post("/auth/telegram", json={"init_data": raw})

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert raw not in response.text
    assert_matches(response, "signInWithTelegram")


async def test_missing_init_data_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/telegram", json={})
    assert response.status_code == 422
    assert_matches(response, "signInWithTelegram")


async def test_me_with_token(client: httpx.AsyncClient) -> None:
    me = await sign_in(client)

    response = await client.get("/me", headers=me.headers)

    assert response.status_code == 200
    assert response.json()["id"] == me.user_id
    assert_matches(response, "getMe")


@pytest.mark.parametrize("header", [None, "Bearer nope", "Basic abc"])
async def test_me_without_valid_token_is_401(client: httpx.AsyncClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    response = await client.get("/me", headers=headers)
    assert response.status_code == 401
    assert_matches(response, "getMe")
