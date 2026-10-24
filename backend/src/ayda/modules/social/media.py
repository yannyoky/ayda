"""Proof photos, videos and circles: a presigned PUT, then a worker job cleans or re-encodes
the file before anyone sees it. A proof has up to 3 photos, or one video, or one circle.
Video files are deleted 30 days after upload; the post stays (ADR 0019)."""

import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.core.storage import UPLOAD_TTL, ObjectMissing, Storage
from ayda.core.transcode import InvalidMedia, transcode_video, transcode_video_note
from ayda.modules.social.images import InvalidImage, clean_photo
from ayda.modules.social.models import Media

MAX_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_UPLOADS_PER_DAY = 30
CONTENT_TYPES = ("image/jpeg", "image/png", "image/heic", "image/webp")
VIDEO_TYPES = ("video/webm", "video/mp4", "video/quicktime")
# kind -> (accepted upload types, largest upload)
KINDS = {
    "photo": (CONTENT_TYPES, MAX_BYTES),
    "video": (VIDEO_TYPES, MAX_VIDEO_BYTES),
    "video_note": (VIDEO_TYPES, MAX_VIDEO_BYTES),
}
UNATTACHED_TTL = timedelta(days=1)
VIDEO_TTL = timedelta(days=30)
PROCESS_JOB = "media.process"


class UploadLimitError(Exception):
    pass


class UnsupportedUpload(ValueError):
    """The content type or size does not fit the kind."""


class MediaError(ValueError):
    """The media can't be attached: unknown, not the owner's, used or failed."""


class MediaMixError(MediaError):
    """A video or a circle goes alone, without photos or another video."""


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


def video_key(media_id: uuid.UUID) -> str:
    return f"videos/{media_id}.mp4"


def media_keys(media: Media) -> set[str]:
    """Every key the media may have in storage: the upload and any processed copy."""
    keys = {upload_key(media.id), photo_key(media.id), video_key(media.id)}
    return keys | ({media.storage_key} if media.storage_key else set())


async def create_upload(
    session: AsyncSession,
    storage: Storage,
    owner_id: uuid.UUID,
    content_type: str,
    size_bytes: int,
    now: datetime,
    kind: str = "photo",
) -> UploadSlot:
    types, max_bytes = KINDS[kind]
    if content_type not in types or size_bytes > max_bytes:
        raise UnsupportedUpload(kind)
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
        kind=kind,
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
    """Lock the owner's unattached media for a post: up to 3 photos, or one video or circle.
    The caller attaches them and enqueues PROCESS_JOB for each one still pending."""
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
    if len(out) > 1 and any(m.kind != "photo" for m in out):
        raise MediaMixError
    return out


async def process(session: AsyncSession, storage: Storage, media_id: uuid.UUID) -> None:
    """Worker job: clean the upload, store the copy, delete the original."""
    media = await session.get(Media, media_id, with_for_update=True)
    if media is None or media.status not in ("pending", "processing"):
        return
    if media.kind != "photo":
        await _process_video(storage, media)
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


async def _process_video(storage: Storage, media: Media) -> None:
    original = upload_key(media.id)
    note = media.kind == "video_note"
    with tempfile.TemporaryDirectory(prefix="ayda-media-") as folder:
        source, target = Path(folder, "upload"), Path(folder, "out")
        try:
            await storage.download_file(original, str(source))
            if source.stat().st_size > MAX_VIDEO_BYTES:
                raise InvalidMedia("too large")
            if note:
                length = await transcode_video_note(source, target)
                width = height = None
            else:
                length, width, height = await transcode_video(source, target)
        except (ObjectMissing, InvalidMedia, OSError):
            media.status = "failed"
            await storage.delete([original])
            return
        await storage.upload_file(str(target), video_key(media.id))
        size = target.stat().st_size
    await storage.delete([original])
    media.storage_key = video_key(media.id)
    media.content_type = "video/mp4"
    media.size_bytes = size
    media.width, media.height = width, height
    media.duration_ms = length
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
    await storage.delete(sorted({k for m in rows for k in media_keys(m)}))
    for media in rows:
        await session.delete(media)
    return len(rows)


async def expire_videos(session: AsyncSession, now: datetime) -> list[str]:
    """Periodic: videos and circles of posts older than 30 days lose their file; the post
    stays and says so. Returns storage keys for the caller to delete."""
    rows = list(
        await session.scalars(
            select(Media)
            .where(
                Media.kind != "photo",
                Media.status != "expired",
                Media.post_id.is_not(None),
                Media.created_at < now - VIDEO_TTL,
            )
            .limit(500)
            .with_for_update(skip_locked=True)
        )
    )
    keys = sorted({k for m in rows for k in media_keys(m)})
    for media in rows:
        media.status = "expired"
        media.storage_key = ""
    return keys


def photo_url(storage: Storage, media: Media) -> str | None:
    """A short-lived URL to the cleaned copy; never to an upload that is not cleaned yet.
    Works for videos too."""
    return storage.presign_get(media.storage_key) if media.status == "ready" else None
