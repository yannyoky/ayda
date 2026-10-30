"""Devices that receive push notifications. A token belongs to one user at a time: when
someone else signs in on the same phone, the token moves to them."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.ids import uuid7
from ayda.modules.auth.models import Device


async def register_device(
    session: AsyncSession, user_id: uuid.UUID, platform: str, token: str
) -> Device:
    now = datetime.now(UTC)
    values = {"user_id": user_id, "platform": platform, "last_seen_at": now}
    device = (
        await session.execute(
            insert(Device)
            .values(id=uuid7(), token=token, created_at=now, **values)
            .on_conflict_do_update(index_elements=[Device.token], set_=values)
            .returning(Device)
        )
    ).scalar_one()
    await session.refresh(device)
    return device


async def list_devices(session: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    rows = await session.scalars(
        select(Device).where(Device.user_id == user_id).order_by(Device.created_at)
    )
    return list(rows)


async def remove_device(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(Device).where(Device.id == device_id, Device.user_id == user_id).returning(Device.id)
    )
    return result.scalar_one_or_none() is not None


async def forget_token(session: AsyncSession, token: str) -> None:
    """FCM said the token is no longer valid (app removed or data cleared)."""
    await session.execute(delete(Device).where(Device.token == token))


async def forget_user_devices(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(Device).where(Device.user_id == user_id))
