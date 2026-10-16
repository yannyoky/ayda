"""Weekly friends ladder. Each user's week starts on Monday 00:00 in their own time zone;
points for personal quests count without details (only totals leave the ledger)."""

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import Ladder, LadderEntry
from ayda.app.feed import user_summary
from ayda.modules import auth, quests, social
from ayda.modules.quests.days import local_now, week_start


def local_today(user: auth.User, now: datetime) -> date:
    """The calendar date, not the quest day: the week turns at Monday midnight."""
    return local_now(now, user.timezone).date()


async def build_ladder(
    session: AsyncSession, me: auth.User, now: datetime, previous: bool = False
) -> Ladder:
    friend_ids = list(await social.friends(session, me.id))
    users = await auth.get_users(session, friend_ids)
    users = {uid: u for uid, u in users.items() if u.deletion_requested_at is None}
    users[me.id] = me
    shift = timedelta(days=7 if previous else 0)
    today = {uid: local_today(u, now) for uid, u in users.items()}
    weeks = {uid: week_start(day) - shift for uid, day in today.items()}
    points = await quests.weekly_points(session, weeks)
    streaks = await quests.streak_views(session, today)

    order = sorted(
        users,
        key=lambda uid: (
            -points[uid],
            -streaks[uid].current_days,
            users[uid].first_name.lower(),
            str(uid),
        ),
    )
    entries = [
        LadderEntry(
            rank=i + 1,
            user=user_summary(users[uid], uid),
            points=points[uid],
            streak_days=streaks[uid].current_days,
            is_me=uid == me.id,
        )
        for i, uid in enumerate(order)
    ]
    return Ladder(week_start=weeks[me.id], entries=entries)
