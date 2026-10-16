"""Bot messages on a schedule: morning and evening reminders, the hourly digest of likes and
comments, and the Sunday ladder summary.

Periodic schedulers (run by the worker every minute or so) queue notifications with dedupe
keys, so a restart or a second worker never sends twice. Skip rules are checked again when
the message is rendered, right before sending. Tone is neutral: no shaming, no pressure.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.app.ladder import build_ladder
from ayda.app.notifications import RENDERERS, Message, Renderer, app_button, notify
from ayda.core.config import Settings
from ayda.modules import auth, quests, social
from ayda.modules.quests.days import local_day, local_now, week_start

# Sends are queued while the local time is within this window after the chosen time.
WINDOW = timedelta(minutes=5)
WEEKLY_SUMMARY_AT = time(20, 0)
MORNING = "reminder.morning"
EVENING = "reminder.evening"
DIGEST = "social.digest"
WEEKLY = "ladder.weekly"
# start_param of reminder buttons, so opening the app from a reminder can be logged.
OPENED_PARAMS = {"r-morning": "morning", "r-evening": "evening"}


def _due(now_local: datetime, at: time) -> bool:
    start = datetime.combine(now_local.date(), at, now_local.tzinfo)
    return start <= now_local < start + WINDOW


async def _reminder_users(session: AsyncSession) -> list[auth.User]:
    rows = await session.scalars(
        select(auth.User).where(
            auth.User.bot_reachable,
            auth.User.deletion_requested_at.is_(None),
            auth.User.onboarded_at.is_not(None),
        )
    )
    return list(rows)


async def schedule_reminders(session: AsyncSession, now: datetime) -> int:
    """Queue morning and evening reminders that are due now; returns how many were new."""
    queued = 0
    for user in await _reminder_users(session):
        now_local = local_now(now, user.timezone)
        day = local_day(now, user.timezone)
        for kind, at in ((MORNING, user.morning_reminder_at), (EVENING, user.evening_reminder_at)):
            if at is None or not _due(now_local, at):
                continue
            key = f"{kind}:{user.id}:{day.isoformat()}"
            if await notify(session, user.id, kind, {"day": day.isoformat()}, dedupe_key=key):
                queued += 1
    return queued


def _day(params: Mapping[str, Any]) -> date:
    return date.fromisoformat(str(params["day"]))


def morning_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        if await quests.get_checkin(session, user.id, _day(params)) is not None:
            return None
        return Message(
            "Доброе утро! Расскажи, как пройдёт день, и я подберу пару дел под него.",
            app_button(settings, "Открыть", start_param="r-morning"),
        )

    return render


def evening_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        day = _day(params)
        if await quests.get_checkin(session, user.id, day) is None:
            return None
        pool = await quests.get_pool(session, user.id, day)
        rows = await quests.day_quests(session, pool.id) if pool else []
        done = [q for q in rows if q.state == "completed"]
        open_ = [q for q in rows if q.state == "taken"]
        if not open_:
            return None
        points, _ = await quests.points_summary(session, user.id, day)
        lines = [f"Итоги дня: выполнено {len(done)}, очков {points}."]
        lines.append("Ещё открыто:")
        lines += [f"• {q.title}" for q in open_]
        lines.append("Успеешь до 4 утра, а если нет, ничего страшного.")
        return Message("\n".join(lines), app_button(settings, "Отметить", start_param="r-evening"))

    return render


# --- hourly digest of likes and comments ------------------------------------------------


def _hour_bucket(now: datetime) -> int:
    """Start of the previous full hour, as a Unix timestamp."""
    return int(now.astimezone(UTC).replace(minute=0, second=0, microsecond=0).timestamp()) - 3600


async def schedule_digests(session: AsyncSession, now: datetime) -> int:
    """For the last full hour, queue one digest per post author who got reactions."""
    start = datetime.fromtimestamp(_hour_bucket(now), UTC)
    authors = await social.reaction_recipients(session, start, start + timedelta(hours=1))
    queued = 0
    for author_id in authors:
        key = f"{DIGEST}:{author_id}:{int(start.timestamp())}"
        if await notify(
            session, author_id, DIGEST, {"from": int(start.timestamp())}, dedupe_key=key
        ):
            queued += 1
    return queued


def digest_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        start = datetime.fromtimestamp(int(params["from"]), UTC)
        likes, comments = await social.reaction_counts(
            session, user.id, start, start + timedelta(hours=1)
        )
        if not likes and not comments:
            return None
        parts: list[str] = []
        if likes:
            parts.append(f"лайков: {likes}")
        if comments:
            parts.append(f"комментариев: {comments}")
        return Message(
            "Друзья отметили твои посты, " + ", ".join(parts) + ".",
            app_button(settings, "Посмотреть"),
        )

    return render


# --- Sunday ladder summary --------------------------------------------------------------


async def schedule_weekly(session: AsyncSession, now: datetime) -> int:
    queued = 0
    for user in await _reminder_users(session):
        now_local = local_now(now, user.timezone)
        if now_local.weekday() != 6 or not _due(now_local, WEEKLY_SUMMARY_AT):
            continue
        week = week_start(now_local.date())
        key = f"{WEEKLY}:{user.id}:{week.isoformat()}"
        if await notify(session, user.id, WEEKLY, {"week": week.isoformat()}, dedupe_key=key):
            queued += 1
    return queued


def weekly_renderer(settings: Settings) -> Renderer:
    async def render(
        session: AsyncSession, user: auth.User, params: Mapping[str, Any]
    ) -> Message | None:
        ladder = await build_ladder(session, user, datetime.now(UTC))
        me = next(e for e in ladder.entries if e.is_me)
        if me.points == 0 and len(ladder.entries) == 1:
            return None
        text = f"Неделя закончилась: у тебя {me.points} очков"
        if len(ladder.entries) > 1:
            text += f", {me.rank} место из {len(ladder.entries)} среди друзей"
        text += ". Новая неделя начинается завтра."
        return Message(text, app_button(settings, "Ладдер"))

    return render


def register(settings: Settings) -> None:
    RENDERERS[MORNING] = morning_renderer(settings)
    RENDERERS[EVENING] = evening_renderer(settings)
    RENDERERS[DIGEST] = digest_renderer(settings)
    RENDERERS[WEEKLY] = weekly_renderer(settings)


def reminder_opened(start_param: str | None) -> str | None:
    return OPENED_PARAMS.get(start_param or "")
