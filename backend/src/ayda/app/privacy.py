"""152-FZ: account deletion and data retention (docs/architecture.md, "Personal data map")."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core import jobs
from ayda.modules import analytics, assistant, auth, chat, habits, quests, social
from ayda.modules.quests import days as day_clock

ERASE_JOB = "account.erase"


async def request_deletion(session: AsyncSession, user: auth.User) -> None:
    """Signs the user out everywhere at once and queues the erasure."""
    await auth.request_deletion(session, user)
    await jobs.enqueue(
        session, ERASE_JOB, {"account": str(user.id)}, dedupe_key=f"{ERASE_JOB}:{user.id}"
    )


async def erase_account(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Erase profile, habits, check-ins, quests, points, posts, comments, likes, friendships,
    photos, messages, chat memberships and the assistant chat; anonymize analytics events.
    Runs in one transaction; photo files are deleted by a follow-up job."""
    user = await auth.get_user(session, user_id)
    if user is None or user.deletion_requested_at is None:
        return False
    keys = await social.erase_user(session, user_id)
    await quests.erase_user(session, user_id)
    await chat.erase_user(session, user_id)
    await assistant.chat.erase_user(session, user_id)
    await habits.erase_user(session, user_id)
    await analytics.anonymize_user(session, user_id)
    await jobs.cancel_for_user(session, str(user_id))
    await auth.delete_user(session, user_id)
    if keys:
        await jobs.enqueue(session, social.DELETE_FILES_JOB, {"keys": keys})
    return True


async def purge_old_checkin_texts(session: AsyncSession, now: datetime) -> int:
    return await quests.purge_checkin_texts(session, now)


# The earliest time zone on Earth: its running day is the oldest one still going anywhere.
_LAST_ZONE = "Etc/GMT+12"


async def purge_old_assistant_chats(session: AsyncSession, now: datetime) -> int:
    """The assistant chat lives for its day (ADR 0013): delete days over in every zone."""
    return await assistant.chat.purge_before(session, day_clock.local_day(now, _LAST_ZONE))
