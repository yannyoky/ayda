import uuid

from fastapi import APIRouter, Response

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import Device, DeviceIn
from ayda.core.problems import Problem
from ayda.modules import auth

router = APIRouter(tags=["profile"])


@router.put("/me/devices", operation_id="registerMyDevice")
async def register_my_device(body: DeviceIn, user: CurrentUser, session: DbSession) -> Device:
    device = await auth.register_device(session, user.id, body.platform, body.token)
    await session.commit()
    return Device(
        id=device.id,
        platform="ios" if device.platform == "ios" else "android",
        created_at=device.created_at,
    )


@router.delete("/me/devices/{device_id}", operation_id="removeMyDevice", status_code=204)
async def remove_my_device(device_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Response:
    if not await auth.remove_device(session, user.id, device_id):
        raise Problem(404, "not-found", detail="Устройство не найдено")
    await session.commit()
    return Response(status_code=204)
