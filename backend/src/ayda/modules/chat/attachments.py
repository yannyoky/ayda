"""Voice messages: a presigned PUT, then a worker job re-encodes the file before anyone
can play it (ADR 0019). The original upload is always deleted."""

import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.core.storage import UPLOAD_TTL, ObjectMissing, Storage
from ayda.modules.chat.audio import InvalidMedia, transcode_voice
from ayda.modules.chat.models import Attachment, Message

MAX_BYTES = 10 * 1024 * 1024
MAX_UPLOADS_PER_DAY = 200
VOICE_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/aac", "audio/mpeg")
UNSENT_TTL = timedelta(days=1)
PROCESS_JOB = "chat.process_attachment"


class AttachmentLimitError(Exception):
    pass


class AttachmentError(ValueError):
    """The attachment can't be sent: unknown, someone else's, another chat's or used."""


@dataclass(frozen=True)
class AttachmentSlot:
    attachment: Attachment
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime


def upload_key(attachment_id: uuid.UUID) -> str:
    return f"chat/uploads/{attachment_id}"


def voice_key(attachment_id: uuid.UUID) -> str:
    return f"chat/voice/{attachment_id}.m4a"


def _keys(attachment: Attachment) -> set[str]:
    return {attachment.storage_key, upload_key(attachment.id), voice_key(attachment.id)}


async def create_upload(
    session: AsyncSession,
    storage: Storage,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
    content_type: str,
    size_bytes: int,
    now: datetime,
) -> AttachmentSlot:
    recent = await session.scalar(
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.owner_id == owner_id, Attachment.created_at > now - timedelta(days=1))
    )
    if (recent or 0) >= MAX_UPLOADS_PER_DAY:
        raise AttachmentLimitError
    attachment_id = uuid7()
    attachment = Attachment(
        id=attachment_id,
        conversation_id=conversation_id,
        owner_id=owner_id,
        kind="voice",
        status="pending",
        storage_key=upload_key(attachment_id),
        content_type=content_type,
        size_bytes=size_bytes,
        created_at=now,
    )
    session.add(attachment)
    await session.flush()
    return AttachmentSlot(
        attachment=attachment,
        upload_url=storage.presign_put(attachment.storage_key, content_type, size_bytes),
        headers={"Content-Type": content_type},
        expires_at=now + UPLOAD_TTL,
    )


async def claim(
    session: AsyncSession, conversation_id: uuid.UUID, owner_id: uuid.UUID, attachment_id: uuid.UUID
) -> Attachment:
    """Lock an unsent upload of this member in this chat before it goes into a message."""
    attachment = await session.get(Attachment, attachment_id, with_for_update=True)
    if (
        attachment is None
        or attachment.owner_id != owner_id
        or attachment.conversation_id != conversation_id
        or attachment.message_id is not None
        or attachment.status != "pending"
    ):
        raise AttachmentError(str(attachment_id))
    return attachment


def attach(attachment: Attachment, message: Message) -> None:
    """The caller enqueues PROCESS_JOB for the attachment after this."""
    attachment.message_id = message.id
    attachment.status = "processing"


async def process(session: AsyncSession, storage: Storage, attachment_id: uuid.UUID) -> int | None:
    """Worker job: re-encode the upload, store the copy, delete the original.
    Returns the message id to tell the chat about, or None when there is nothing to do."""
    attachment = await session.get(Attachment, attachment_id, with_for_update=True)
    if attachment is None or attachment.status != "processing":
        return None
    original = upload_key(attachment.id)
    with tempfile.TemporaryDirectory(prefix="ayda-voice-") as folder:
        source, target = Path(folder, "upload"), Path(folder, "voice.m4a")
        try:
            await storage.download_file(original, str(source))
            if source.stat().st_size > MAX_BYTES:
                raise InvalidMedia("too large")
            length = await transcode_voice(source, target)
        except (ObjectMissing, InvalidMedia, OSError):
            attachment.status = "failed"
            await storage.delete([original])
            return attachment.message_id
        await storage.upload_file(str(target), voice_key(attachment.id))
        size = target.stat().st_size
    await storage.delete([original])
    attachment.storage_key = voice_key(attachment.id)
    attachment.content_type = "audio/mp4"
    attachment.size_bytes = size
    attachment.duration_ms = length
    attachment.status = "ready"
    return attachment.message_id


async def for_messages(session: AsyncSession, message_ids: Sequence[int]) -> dict[int, Attachment]:
    if not message_ids:
        return {}
    rows = await session.scalars(select(Attachment).where(Attachment.message_id.in_(message_ids)))
    return {a.message_id: a for a in rows if a.message_id is not None}


async def _remove(session: AsyncSession, rows: Sequence[Attachment]) -> list[str]:
    keys = sorted({k for a in rows for k in _keys(a)})
    if rows:
        await session.execute(delete(Attachment).where(Attachment.id.in_([a.id for a in rows])))
    return keys


async def remove_for_message(session: AsyncSession, message_id: int) -> list[str]:
    """Delete the message's attachment row; returns storage keys for the caller to delete."""
    rows = list(
        await session.scalars(select(Attachment).where(Attachment.message_id == message_id))
    )
    return await _remove(session, rows)


async def remove_for_conversations(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> list[str]:
    if not conversation_ids:
        return []
    rows = list(
        await session.scalars(
            select(Attachment).where(Attachment.conversation_id.in_(conversation_ids))
        )
    )
    return await _remove(session, rows)


async def remove_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[str]:
    rows = list(await session.scalars(select(Attachment).where(Attachment.owner_id == owner_id)))
    return await _remove(session, rows)


async def remove_unsent(session: AsyncSession, now: datetime) -> list[str]:
    """Periodic: uploads never sent within a day."""
    rows = list(
        await session.scalars(
            select(Attachment)
            .where(Attachment.message_id.is_(None), Attachment.created_at < now - UNSENT_TTL)
            .limit(500)
        )
    )
    return await _remove(session, rows)


def play_url(storage: Storage, attachment: Attachment) -> str | None:
    """A short-lived URL to the re-encoded copy; never to an upload that is not processed."""
    return storage.presign_get(attachment.storage_key) if attachment.status == "ready" else None
