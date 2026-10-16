"""A real Centrifugo for integration tests and a tiny client speaking its JSON WebSocket
protocol. CI runs a service container; locally `docker compose up -d centrifugo` (its default
secrets match the defaults here)."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from websockets.asyncio.client import ClientConnection, connect

CENTRIFUGO_URL = os.environ.get("TEST_CENTRIFUGO_URL", "http://localhost:8001")
CENTRIFUGO_API_KEY = os.environ.get("TEST_CENTRIFUGO_API_KEY", "change-me")
CENTRIFUGO_TOKEN_SECRET = os.environ.get("TEST_CENTRIFUGO_TOKEN_SECRET", "change-me")


def require_centrifugo() -> None:
    """Skip when no Centrifugo runs locally; CI sets REQUIRE_CENTRIFUGO=1 so it never skips."""
    try:
        httpx.post(
            f"{CENTRIFUGO_URL}/api/info",
            json={},
            headers={"X-API-Key": CENTRIFUGO_API_KEY},
            timeout=2,
        ).raise_for_status()
    except httpx.HTTPError:
        if os.environ.get("REQUIRE_CENTRIFUGO") == "1":
            raise
        pytest.skip("Centrifugo is not running (docker compose up -d centrifugo)")


class Client:
    def __init__(self, ws: ClientConnection) -> None:
        self._ws = ws
        self._next_id = 0
        self.pushes: list[dict[str, Any]] = []

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        await self._ws.send(json.dumps({"id": self._next_id, method: params}))
        while True:
            reply = json.loads(await self._ws.recv(decode=True))
            if reply.get("id") == self._next_id:
                return reply
            if "push" in reply:
                self.pushes.append(reply["push"])

    async def push(self, timeout: float = 2.0) -> dict[str, Any]:
        if self.pushes:
            return self.pushes.pop(0)
        async with asyncio.timeout(timeout):
            while True:
                reply = json.loads(await self._ws.recv(decode=True))
                if "push" in reply:
                    return reply["push"]


@asynccontextmanager
async def centrifugo_client(url: str, token: str) -> AsyncIterator[Client]:
    async with connect(url, open_timeout=3) as ws:
        client = Client(ws)
        reply = await client.call("connect", {"token": token})
        assert "connect" in reply, reply
        yield client
