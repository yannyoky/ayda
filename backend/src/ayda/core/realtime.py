"""Realtime delivery through Centrifugo (ADR 0007).

Every user has one personal channel, `personal:#<user id>`. Centrifugo lets only a connection
whose token carries that user id subscribe to it, so the backend decides who gets each event
by choosing the channels it broadcasts to.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt

from ayda.core.config import Settings

log = logging.getLogger(__name__)

PERSONAL_NAMESPACE = "personal"
TOKEN_TTL = timedelta(hours=1)
BROADCAST_TIMEOUT_S = 2.0


class RealtimeUnavailable(Exception):
    """Centrifugo is not configured, unreachable or refused the call."""


def personal_channel(user_id: uuid.UUID) -> str:
    return f"{PERSONAL_NAMESPACE}:#{user_id}"


@dataclass(frozen=True)
class ConnectionToken:
    token: str
    expires_at: datetime
    url: str
    channel: str


def connection_token(settings: Settings, user_id: uuid.UUID, now: datetime) -> ConnectionToken:
    if settings.centrifugo_token_secret is None:
        raise RealtimeUnavailable("no token secret")
    expires_at = now + TOKEN_TTL
    token = jwt.encode(
        {"sub": str(user_id), "exp": int(expires_at.timestamp())},
        settings.centrifugo_token_secret.get_secret_value(),
        algorithm="HS256",
    )
    return ConnectionToken(
        token, expires_at, settings.centrifugo_public_url, personal_channel(user_id)
    )


class Realtime:
    """Centrifugo server API client. Without an API key it does nothing (local dev, tests)."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._url = settings.centrifugo_api_url.rstrip("/")
        key = settings.centrifugo_api_key
        self._headers = {"X-API-Key": key.get_secret_value()} if key is not None else None
        self._http = http or httpx.AsyncClient()
        self._own_http = http is None

    @property
    def enabled(self) -> bool:
        return self._headers is not None

    async def broadcast(self, user_ids: Iterable[uuid.UUID], event: Mapping[str, Any]) -> None:
        """Publish one event to the personal channels of these users."""
        channels = [personal_channel(u) for u in dict.fromkeys(user_ids)]
        if not channels or self._headers is None:
            return
        try:
            response = await self._http.post(
                f"{self._url}/broadcast",
                json={"channels": channels, "data": dict(event)},
                headers=self._headers,
                timeout=BROADCAST_TIMEOUT_S,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RealtimeUnavailable(type(exc).__name__) from None
        if "error" in body:
            raise RealtimeUnavailable(f"api error {body['error'].get('code')}")
        failed = [r for r in body.get("result", {}).get("responses", []) if "error" in r]
        if failed:
            # Per-channel errors (e.g. an unknown namespace) are a configuration problem.
            raise RealtimeUnavailable(f"{len(failed)} channels failed")

    async def aclose(self) -> None:
        if self._own_http:
            await self._http.aclose()
