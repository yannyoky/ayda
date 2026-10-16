import json
import time
from dataclasses import dataclass

import httpx

from ayda.modules.auth.telegram import sign

TEST_BOT_TOKEN = "123456:TEST-TOKEN"


def make_init_data(
    telegram_id: int = 1001,
    first_name: str = "Саша",
    *,
    auth_date: int | None = None,
    bot_token: str = TEST_BOT_TOKEN,
    start_param: str | None = None,
    photo_url: str | None = None,
) -> str:
    user: dict[str, object] = {"id": telegram_id, "first_name": first_name, "language_code": "ru"}
    if photo_url:
        user["photo_url"] = photo_url
    fields = {
        "query_id": "AAH1",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    if start_param:
        fields["start_param"] = start_param
    fields["hash"] = sign(fields, bot_token)
    return str(httpx.QueryParams(fields))


@dataclass
class SignedIn:
    user_id: str
    headers: dict[str, str]


async def sign_in(
    client: httpx.AsyncClient, telegram_id: int = 1001, name: str = "Саша"
) -> SignedIn:
    response = await client.post(
        "/auth/telegram", json={"init_data": make_init_data(telegram_id, name)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return SignedIn(body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"})
