from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import Me, Reminders
from ayda.modules import auth


def format_local_time(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


async def build_me(session: AsyncSession, user: auth.User) -> Me:
    return Me(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        avatar_url=user.avatar_url,
        city=None,
        timezone=user.timezone,
        theme="plum" if user.theme == "plum" else "graphite",
        reminders=Reminders(
            morning_at=format_local_time(user.morning_reminder_at),
            evening_at=format_local_time(user.evening_reminder_at),
        ),
        consent_required=await auth.consent_required(session, user.id),
        onboarded=user.onboarded_at is not None,
    )
