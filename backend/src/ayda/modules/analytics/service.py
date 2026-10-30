import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.analytics.models import Event


class EventType(StrEnum):
    """Event types (docs/prd.md, "Events"). Bump SCHEMA_VERSIONS when a payload changes."""

    CHECKIN_SUBMITTED = "checkin_submitted"
    POOL_SHOWN = "pool_shown"
    QUEST_TAKEN = "quest_taken"
    QUEST_REJECTED = "quest_rejected"
    QUEST_COMPLETED = "quest_completed"
    PROOF_POSTED = "proof_posted"
    REACTION_ADDED = "reaction_added"
    REMINDER_SENT = "reminder_sent"
    REMINDER_OPENED = "reminder_opened"
    MESSAGE_SENT = "message_sent"
    COOP_CREATED = "coop_created"
    COOP_ANSWERED = "coop_answered"
    COOP_BONUS = "coop_bonus"
    COOP_PART_OPENED = "coop_part_opened"
    COOP_PART_COMPLETED = "coop_part_completed"
    COOP_PART_HANDED_OFF = "coop_part_handed_off"
    COOP_HANDOFF_ANSWERED = "coop_handoff_answered"
    MEETUP_SUGGESTED = "meetup_suggested"
    RECIPES_SUGGESTED = "recipes_suggested"
    RECIPE_PLANNED = "recipe_planned"
    ASSISTANT_MESSAGE = "assistant_message"
    SIGNED_IN = "signed_in"


SCHEMA_VERSIONS: dict[EventType, int] = dict.fromkeys(EventType, 1) | {
    # v2 (M3): event listing ids next to template ids.
    # v2 (M5): co-op kind and part count.
    EventType.COOP_CREATED: 2,
    EventType.POOL_SHOWN: 2,
    EventType.QUEST_TAKEN: 2,
    EventType.QUEST_REJECTED: 2,
    EventType.QUEST_COMPLETED: 2,
}

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


async def count_since(
    session: AsyncSession, user_id: uuid.UUID, type: EventType, since: datetime
) -> int:
    """How many events of this type the user has had since `since` (e.g. for daily limits)."""
    found = await session.scalar(
        select(func.count())
        .select_from(Event)
        .where(Event.user_id == user_id, Event.type == type.value, Event.occurred_at >= since)
    )
    return found or 0


async def anonymize_user(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    """Replace the user's id with one random id in their events and in others' payloads,
    so behavior stays countable but is no longer linked to the person."""
    alias = uuid.uuid4()
    await session.execute(text("SET LOCAL ayda.analytics_maintenance = 'on'"))
    await session.execute(update(Event).where(Event.user_id == user_id).values(user_id=alias))
    await session.execute(
        text(
            "UPDATE analytics.events"
            " SET payload = jsonb_set(payload, '{post_author_id}', to_jsonb(CAST(:alias AS text)))"
            " WHERE payload->>'post_author_id' = :uid"
        ),
        {"alias": str(alias), "uid": str(user_id)},
    )
    return alias
