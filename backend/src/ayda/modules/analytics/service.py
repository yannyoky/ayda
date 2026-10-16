import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.analytics.models import Event


class EventType(StrEnum):
    """M1 event types (docs/prd.md, "Events"). Bump SCHEMA_VERSIONS when a payload changes."""

    CHECKIN_SUBMITTED = "checkin_submitted"
    POOL_SHOWN = "pool_shown"
    QUEST_TAKEN = "quest_taken"
    QUEST_REJECTED = "quest_rejected"
    QUEST_COMPLETED = "quest_completed"
    PROOF_POSTED = "proof_posted"
    REACTION_ADDED = "reaction_added"
    REMINDER_SENT = "reminder_sent"
    REMINDER_OPENED = "reminder_opened"


SCHEMA_VERSIONS: dict[EventType, int] = dict.fromkeys(EventType, 1)

# Keys that would carry raw personal data. Matched case-insensitively against
# every key at any depth, ignoring `_` and `-`.
DENYLIST_KEYS = frozenset(
    {
        "text",
        "caption",
        "comment",
        "message",
        "initdata",
        "hash",
        "token",
        "accesstoken",
        "lat",
        "lon",
        "lng",
        "latitude",
        "longitude",
        "coordinates",
        "location",
        "geo",
        "url",
        "photourl",
        "avatarurl",
        "uploadurl",
        "storagekey",
        "name",
        "firstname",
        "lastname",
        "username",
        "phone",
        "email",
        "telegramid",
        "title",
    }
)

# Values are ids, enum codes and numbers; strings are short codes or UUIDs, never prose.
_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

Scalar = str | int | float | bool | None


class PayloadError(ValueError):
    """The payload could carry personal data or free text."""


def _check(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(key, str):
                raise PayloadError(f"{path}: keys must be strings")
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in DENYLIST_KEYS or normalized.endswith(("text", "url")):
                raise PayloadError(f"{path}.{key}: key is not allowed in events")
            _check(inner, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for i, inner in enumerate(value):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            _check(inner, f"{path}[{i}]")
    elif isinstance(value, str):
        if not _CODE.match(value):
            raise PayloadError(f"{path}: strings must be ids or codes")
    elif value is not None and not isinstance(value, int | float | bool):
        raise PayloadError(f"{path}: unsupported type {type(value).__name__}")


def validate_payload(payload: dict[str, Any]) -> None:
    _check(payload, "payload")


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


async def record(
    session: AsyncSession,
    type: EventType,
    user_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Add an event to the session; it is written with the caller's transaction."""
    data: dict[str, Any] = _jsonable(payload or {})
    validate_payload(data)
    event = Event(
        user_id=user_id,
        type=type.value,
        schema_version=SCHEMA_VERSIONS[type],
        payload=data,
    )
    if occurred_at is not None:
        event.occurred_at = occurred_at
    session.add(event)
