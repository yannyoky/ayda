"""Photo uploads: a presigned PUT, then a worker job cleans the photo before anyone sees it."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.core.storage import UPLOAD_TTL, ObjectMissing, Storage
from ayda.modules.social.images import InvalidImage, clean_photo
from ayda.modules.social.models import Media

MAX_BYTES = 10 * 1024 * 1024
MAX_UPLOADS_PER_DAY = 30
CONTENT_TYPES = ("image/jpeg", "image/png", "image/heic", "image/webp")
UNATTACHED_TTL = timedelta(days=1)
PROCESS_JOB = "media.process"


class UploadLimitError(Exception):
    pass


class MediaError(ValueError):
    """The media can't be attached: unknown, not the owner's, used or failed."""


@dataclass(frozen=True)
class UploadSlot:
    media: Media
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime


def upload_key(media_id: uuid.UUID) -> str:
    return f"uploads/{media_id}"


def photo_key(media_id: uuid.UUID) -> str:
    return f"photos/{media_id}.jpg"


async def create_upload(
    session: AsyncSession,
    storage: Storage,
    owner_id: uuid.UUID,
    content_type: str,
    size_bytes: int,
    now: datetime,
) -> UploadSlot:
    recent = await session.scalar(
        select(func.count())
        .select_from(Media)
        .where(Media.owner_id == owner_id, Media.created_at > now - timedelta(days=1))
    )
    if (recent or 0) >= MAX_UPLOADS_PER_DAY:
        raise UploadLimitError
    media_id = uuid7()
    media = Media(
        id=media_id,
        owner_id=owner_id,
        storage_key=upload_key(media_id),
        content_type=content_type,
        size_bytes=size_bytes,
        status="pending",
        created_at=now,
    )
    session.add(media)
    await session.flush()
    return UploadSlot(
        media=media,
        upload_url=storage.presign_put(media.storage_key, content_type, size_bytes),
        headers={"Content-Type": content_type},
        expires_at=now + UPLOAD_TTL,
    )


async def claim_media(
    session: AsyncSession, owner_id: uuid.UUID, media_ids: Sequence[uuid.UUID]
) -> list[Media]:
    """Lock the owner's unattached photos for a post; pending ones move to processing.
    The caller attaches them and enqueues PROCESS_JOB for each id in `to_process`."""
    rows = list(
        await session.scalars(select(Media).where(Media.id.in_(media_ids)).with_for_update())
    )
    by_id = {m.id: m for m in rows}
    out: list[Media] = []
    for media_id in media_ids:
        media = by_id.get(media_id)
        if (
            media is None
            or media.owner_id != owner_id
            or media.post_id is not None
            or media.status == "failed"
        ):
            raise MediaError(str(media_id))
        out.append(media)
    return out


async def process(session: AsyncSession, storage: Storage, media_id: uuid.UUID) -> None:
    """Worker job: clean the upload, store the copy, delete the original."""
    media = await session.get(Media, media_id, with_for_update=True)
    if media is None or media.status not in ("pending", "processing"):
        return
    original = upload_key(media.id)
    try:
        data = await storage.get(original, MAX_BYTES)
        if len(data) > MAX_BYTES:
            raise InvalidImage("too large")
        jpeg, width, height = clean_photo(data)
    except (ObjectMissing, InvalidImage):
        media.status = "failed"
        await storage.delete([original])
        return
    await storage.put(photo_key(media.id), jpeg, "image/jpeg")
    await storage.delete([original])
    media.storage_key = photo_key(media.id)
    media.content_type = "image/jpeg"
    media.size_bytes = len(jpeg)
    media.width, media.height = width, height
    media.status = "ready"


async def delete_unattached(session: AsyncSession, storage: Storage, now: datetime) -> int:
    """Periodic: photos never attached to a post within a day are deleted with their files."""
    rows = list(
        await session.scalars(
            select(Media)
            .where(Media.post_id.is_(None), Media.created_at < now - UNATTACHED_TTL)
            .limit(500)
        )
    )
    keys = [k for m in rows for k in {m.storage_key, upload_key(m.id), photo_key(m.id)}]
    await storage.delete(keys)
    for media in rows:
        await session.delete(media)
    return len(rows)


def photo_url(storage: Storage, media: Media) -> str | None:
    """A short-lived URL to the cleaned copy; never to an upload that is not cleaned yet."""
    return storage.presign_get(media.storage_key) if media.status == "ready" else None
