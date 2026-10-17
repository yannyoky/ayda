"""One way to message users: other code calls `notify`, the worker sends.

Jobs carry the user id, a message kind and ids or numbers; the text is rendered at send time
from current data, so no personal text sits in the queue. Kinds register a renderer in
RENDERERS.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core import jobs
from ayda.core.config import Settings
from ayda.modules import analytics, auth
from ayda.modules.analytics import EventType

log = logging.getLogger(__name__)

SEND_JOB = "notify.send"


@dataclass(frozen=True)
class Button:
    text: str
    url: str
    web_app: bool = False


@dataclass(frozen=True)
class Message:
    text: str
    button: Button | None = None


class Unreachable(Exception):
    """The user blocked the bot or the chat does not exist."""


class RetryLater(Exception):
    """Telegram asked to slow down; the job is retried with backoff."""


class Sender(Protocol):
    async def send(self, chat_id: int, message: Message) -> None: ...


Renderer = Callable[[AsyncSession, auth.User, Mapping[str, Any]], Awaitable[Message | None]]
# kind -> renderer; None from a renderer means "nothing to say anymore", so the send is skipped.
RENDERERS: dict[str, Renderer] = {}


def app_button(settings: Settings, text: str, start_param: str | None = None) -> Button:
    if settings.miniapp_url and start_param is None:
        return Button(text, settings.miniapp_url, web_app=True)
    url = f"https://t.me/{settings.telegram_bot_username}?startapp"
    return Button(text, f"{url}={start_param}" if start_param else url)


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    params: Mapping[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    run_at: datetime | None = None,
) -> bool:
    return await jobs.enqueue(
        session,
        SEND_JOB,
        {"user_id": str(user_id), "kind": kind, "params": dict(params or {})},
        dedupe_key=dedupe_key,
        run_at=run_at,
        max_attempts=3,
    )


@dataclass
class SendResult:
    sent: bool
    reason: str | None = None


async def send(session: AsyncSession, sender: Sender, payload: Mapping[str, Any]) -> SendResult:
    user = await auth.get_user(session, uuid.UUID(payload["user_id"]))
    if user is None or user.deletion_requested_at is not None:
        return SendResult(False, "no-user")
    if user.telegram_id is None:
        return SendResult(False, "no-telegram")
    if not user.bot_reachable:
        return SendResult(False, "unreachable")
    message = await RENDERERS[payload["kind"]](session, user, payload.get("params", {}))
    if message is None:
        return SendResult(False, "nothing-to-say")
    try:
        await sender.send(user.telegram_id, message)
    except Unreachable:
        user.bot_reachable = False
        return SendResult(False, "unreachable")
    await analytics.record(session, EventType.REMINDER_SENT, user.id, {"kind": payload["kind"]})
    return SendResult(True)


class RateLimiter:
    """Telegram allows about 30 messages a second overall and 1 a second per chat."""

    def __init__(self, per_second: float = 25, per_chat_s: float = 1.0) -> None:
        self._interval = 1 / per_second
        self._per_chat_s = per_chat_s
        self._next = 0.0
        self._chat_next: dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, chat_id: int) -> None:
        async with self._lock:
            now = time.monotonic()
            at = max(now, self._next, self._chat_next.get(chat_id, 0.0))
            self._next = at + self._interval
            self._chat_next[chat_id] = at + self._per_chat_s
        if at > now:
            await asyncio.sleep(at - now)


class LogSender:
    """Development without a bot token: logs that a message would go out, never its text."""

    async def send(self, chat_id: int, message: Message) -> None:
        log.info("would send a %d-character message", len(message.text))
