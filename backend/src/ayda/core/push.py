"""Push notifications through Firebase Cloud Messaging HTTP v1 (ADR 0009).

A push carries a generic title and body and a few ids; names and message texts are never
sent through Google. The service-account key comes from FCM_SERVICE_ACCOUNT_JSON.
"""

import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

log = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class Push:
    title: str
    body: str
    data: Mapping[str, str] = field(default_factory=dict[str, str])


class InvalidToken(Exception):
    """The device token is no longer registered; forget it."""


class PushRetryLater(Exception):
    """FCM is unavailable or rate-limits; retry the job later."""


class PushError(Exception):
    """Anything else FCM refused; the message never contains the token."""


class FcmSender:
    def __init__(self, service_account_json: str, http: httpx.AsyncClient | None = None) -> None:
        info: dict[str, Any] = json.loads(service_account_json)
        self._email: str = info["client_email"]
        self._key: str = info["private_key"]
        self._project: str = info["project_id"]
        self._token_uri: str = info.get("token_uri", _TOKEN_URI)
        self._http = http or httpx.AsyncClient(timeout=10)
        self._access: tuple[str, float] | None = None

    async def _access_token(self) -> str:
        if self._access and self._access[1] - 60 > time.time():
            return self._access[0]
        now = int(time.time())
        assertion = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            {
                "iss": self._email,
                "scope": _SCOPE,
                "aud": self._token_uri,
                "iat": now,
                "exp": now + 3600,
            },
            self._key,
            algorithm="RS256",
        )
        response = await self._http.post(
            self._token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        if response.status_code != 200:
            raise PushRetryLater(f"oauth {response.status_code}")
        body: dict[str, Any] = response.json()
        self._access = (str(body["access_token"]), now + float(body.get("expires_in", 3600)))
        return self._access[0]

    async def send(self, token: str, push: Push) -> None:
        message = {
            "message": {
                "token": token,
                "notification": {"title": push.title, "body": push.body},
                "data": dict(push.data),
                "android": {"priority": "high"},
            }
        }
        try:
            response = await self._http.post(
                f"https://fcm.googleapis.com/v1/projects/{self._project}/messages:send",
                headers={"Authorization": f"Bearer {await self._access_token()}"},
                json=message,
            )
        except httpx.HTTPError:
            raise PushRetryLater("network") from None
        if response.status_code == 200:
            return
        if response.status_code == 404 or (
            response.status_code == 400 and "UNREGISTERED" in response.text
        ):
            raise InvalidToken
        if response.status_code == 401:
            self._access = None
            raise PushRetryLater("auth")
        if response.status_code in (429, 500, 502, 503, 504):
            raise PushRetryLater(str(response.status_code))
        raise PushError(str(response.status_code))


class LogPushSender:
    """Development without FCM: logs that a push would go out, never its content."""

    async def send(self, token: str, push: Push) -> None:
        log.info("would push a %d-character notification", len(push.body))
