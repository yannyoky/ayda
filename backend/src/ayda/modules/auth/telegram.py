"""Validation of Telegram Mini App initData.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qsl

MAX_AGE = timedelta(hours=24)


class InitDataError(Exception):
    """initData is malformed, forged or too old. The message never contains the data."""


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    photo_url: str | None


@dataclass(frozen=True)
class InitData:
    user: TelegramUser
    auth_date: datetime
    start_param: str | None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign(fields: dict[str, str], bot_token: str) -> str:
    """The `hash` Telegram would put into initData with these fields (used by tests)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    return hmac.new(_secret_key(bot_token), check.encode(), hashlib.sha256).hexdigest()


def _opt_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def validate_init_data(raw: str, bot_token: str, now: datetime | None = None) -> InitData:
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InitDataError("malformed") from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise InitDataError("duplicate keys")
    received = fields.pop("hash", None)
    if not received:
        raise InitDataError("no hash")
    if not hmac.compare_digest(sign(fields, bot_token), received):
        raise InitDataError("bad signature")

    try:
        auth_date = datetime.fromtimestamp(int(fields["auth_date"]), UTC)
    except (KeyError, ValueError, OverflowError, OSError):
        raise InitDataError("bad auth_date") from None
    now = now or datetime.now(UTC)
    if now - auth_date > MAX_AGE or auth_date - now > timedelta(minutes=5):
        raise InitDataError("expired")

    try:
        user_raw: Any = json.loads(fields["user"])
    except (KeyError, ValueError):
        raise InitDataError("no user") from None
    if not isinstance(user_raw, dict):
        raise InitDataError("no user")
    user_data = cast(dict[str, Any], user_raw)
    user_id = user_data.get("id")
    first_name = user_data.get("first_name")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or not isinstance(first_name, str):
        raise InitDataError("bad user")

    return InitData(
        user=TelegramUser(
            id=user_id,
            first_name=first_name,
            last_name=_opt_str(user_data, "last_name"),
            username=_opt_str(user_data, "username"),
            photo_url=_opt_str(user_data, "photo_url"),
        ),
        auth_date=auth_date,
        start_param=_opt_str(fields, "start_param"),
    )
