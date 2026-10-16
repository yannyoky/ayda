from datetime import UTC, datetime

from fastapi import APIRouter, Request

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import UploadInput, UploadSlot
from ayda.core.problems import Problem
from ayda.core.storage import Storage
from ayda.modules import social

router = APIRouter(tags=["media"])


@router.post("/media/uploads", operation_id="createUpload", status_code=201)
async def create_upload(
    body: UploadInput, user: CurrentUser, session: DbSession, request: Request
) -> UploadSlot:
    storage: Storage = request.app.state.storage
    try:
        slot = await social.create_upload(
            session, storage, user.id, body.content_type, body.size_bytes, datetime.now(UTC)
        )
    except social.UploadLimitError:
        raise Problem(429, "too-many-uploads", detail="Слишком много фото за сутки") from None
    await session.commit()
    return UploadSlot(
        media_id=slot.media.id,
        upload_url=slot.upload_url,
        headers=slot.headers,
        expires_at=slot.expires_at,
    )
