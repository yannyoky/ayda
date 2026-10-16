"""The user's day: morning check-in, the quest pool, taking, replacing and own quests.

Code picks the candidates (goals, free time, weather, recent history); the assistant only
parses the check-in and orders candidates; without it the code ranking is used.
"""

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import (
    Category,
    Checkin,
    CheckinInput,
    CompleteQuestInput,
    Completion,
    Day,
    DayLimits,
    DayQuest,
    OwnQuestInput,
    PointsBreakdown,
    Replacement,
    Streak,
    Weather,
)
from ayda.app.coop import COOP_UPDATED, record_bonuses
from ayda.app.day_problems import day_problem
from ayda.app.realtime import publish
from ayda.core import jobs
from ayda.core.problems import Problem
from ayda.core.realtime import Realtime
from ayda.modules import analytics, assistant, auth, events, habits, quests, social
from ayda.modules.analytics import EventType
from ayda.modules.quests import days as day_clock
from ayda.modules.quests.day_service import DayError, NewQuest
from ayda.modules.quests.scoring import base_points, scoring_config
from ayda.modules.quests.selection import (
    CODE_WHY,
    DayConditions,
    WeatherFlags,
    code_rank,
    select_candidates,
)

POOL_DEADLINE_S = 9.0
PARSE_DEADLINE_S = 4.0
MAX_TASK_QUESTS = 5
DAY_MINUTES = 15 * 60  # 08:00-23:00
TASK_WHY = "Это из твоего плана на сегодня."


@dataclass(frozen=True)
class DayTools:
    assistant: assistant.Assistant
    weather: events.WeatherClient


# --- check-in parsing without the LLM -------------------------------------------------

_CATEGORY_HINTS: tuple[tuple[Category, tuple[str, ...]], ...] = (
    ("sport", ("трен", "спорт", "бег", "зал", "йог", "бассейн", "зарядк")),
    ("walk", ("гуля", "прогул", "пешком", "шаг")),
    ("social", ("друз", "встреч", "созвон", "позвон", "мам", "пап", "семь")),
    ("learning", ("учи", "урок", "курс", "книг", "чита", "лекци", "экзамен")),
    ("home", ("убор", "стир", "готов", "посуд", "магазин", "продукт", "ремонт")),
    ("rest", ("отдох", "отдых", "спать", "выспат", "сон")),
    ("city", ("музей", "выставк", "театр", "кино", "концерт")),
)
_TIME = re.compile(r"\b([01]?[0-9]|2[0-3])[:.]([0-5][0-9])\b")
_WINDOW = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def guess_category(title: str) -> Category:
    lowered = title.lower()
    for category, hints in _CATEGORY_HINTS:
        if any(h in lowered for h in hints):
            return category
    return "project"


def parse_without_llm(text: str) -> assistant.ParsedCheckin:
    """Each line becomes a task; the time after 18:00 counts as free."""
    tasks: list[assistant.ParsedTask] = []
    for line in text.splitlines():
        title = line.strip(" \t-*•.").strip()
        if not title:
            continue
        match = _TIME.search(title)
        at = f"{int(match[1]):02d}:{match[2]}" if match else None
        tasks.append(
            assistant.ParsedTask(
                title=title[:120], category=guess_category(title), duration_min=30, at=at
            )
        )
        if len(tasks) == 10:
            break
    return assistant.ParsedCheckin(tasks=tasks, busy=[], free_evening=True)


def free_minutes(parsed: assistant.ParsedCheckin) -> int:
    busy = 0
    for window in parsed.busy:
        m = _WINDOW.match(window)
        if m:
            start = int(m[1]) * 60 + int(m[2])
            end = int(m[3]) * 60 + int(m[4])
            busy += max(end - start, 0)
    return max(DAY_MINUTES - busy, 60)


def max_duration(parsed: assistant.ParsedCheckin) -> int:
    longest = min(free_minutes(parsed), 480)
    return longest if parsed.free_evening else min(longest, 60)


# --- reading the day --------------------------------------------------------------------


def quest_schema(
    quest: quests.DayQuest, points: int | None = None, coop_id: uuid.UUID | None = None
) -> DayQuest:
    return DayQuest(
        id=quest.id,
        source=quest.source,  # pyright: ignore[reportArgumentType]
        title=quest.title,
        description=quest.description,
        category=quest.category,  # pyright: ignore[reportArgumentType]
        duration_min=quest.duration_min,
        base_points=base_points(quest.duration_min),
        why=quest.why,
        outdoor=quest.outdoor,
        state=quest.state,  # pyright: ignore[reportArgumentType]
        visibility=quest.visibility,  # pyright: ignore[reportArgumentType]
        points_awarded=points,
        expires_at=quest.expires_at,
        coop_id=coop_id,
    )


def streak_schema(streak: quests.StreakView) -> Streak:
    return Streak(
        current_days=streak.current_days,
        best_days=streak.best_days,
        freeze_available=streak.freeze_available,
    )


async def build_day(session: AsyncSession, user: auth.User, now: datetime) -> Day:
    day = day_clock.local_day(now, user.timezone)
    checkin = await quests.get_checkin(session, user.id, day)
    pool = await quests.get_pool(session, user.id, day)
    rows = await quests.day_quests(session, pool.id) if pool else []
    awarded = await quests.points_by_quest(session, [q.id for q in rows])
    coops = await quests.coop.coops_by_quest(session, [q.id for q in rows])
    points_today, points_week = await quests.points_summary(session, user.id, day)
    streak = await quests.streak_view(session, user.id, day)
    weather = pool.weather if pool and pool.weather else None
    return Day(
        local_date=day,
        checkin=Checkin(
            text=checkin.text or "",
            mood=checkin.mood,  # pyright: ignore[reportArgumentType]
            submitted_at=checkin.updated_at,
        )
        if checkin
        else None,
        pool_status=pool.status if pool else "none",  # pyright: ignore[reportArgumentType]
        weather=Weather(
            temperature_c=weather["temperature_c"],
            condition=weather["condition"],
        )
        if weather
        else None,
        quests=[
            quest_schema(q, awarded.get(q.id), coops.get(q.id))
            for q in rows
            if q.state != "replaced"
        ],
        limits=DayLimits(
            taken=sum(q.state in quests.ACTIVE_STATES for q in rows),
            max_taken=scoring_config().max_taken_per_day,
            replacements_left=quests.replacements_left(pool),
        ),
        points_today=points_today,
        points_week=points_week,
        streak=streak_schema(streak),
    )


# --- the morning check-in and the pool ------------------------------------------------


async def _today_weather(
    session: AsyncSession, user: auth.User, tools: DayTools, now: datetime
) -> events.Weather | None:
    if user.city_id is None:
        return None
    point = await events.city_point(session, user.city_id)
    if point is None:
        return None
    return await tools.weather.today(user.city_id, point.lat, point.lon, user.timezone, now)


async def submit_checkin(
    session: AsyncSession, user: auth.User, body: CheckinInput, tools: DayTools, now: datetime
) -> Day:
    started = time.monotonic()
    day = day_clock.local_day(now, user.timezone)
    existing = await quests.get_checkin(session, user.id, day)
    if existing is not None and existing.submissions >= quests.MAX_CHECKINS_PER_DAY:
        raise day_problem(DayError("too-many-checkins"))

    text = body.text.strip()
    parsed: assistant.ParsedCheckin | None = None
    if text:
        result = await assistant.parse_checkin(
            tools.assistant, text, body.mood, deadline_s=PARSE_DEADLINE_S
        )
        parsed = result.value if result else None
    parsed_by = "llm" if parsed else "code"
    parsed = parsed or parse_without_llm(text)

    goals = await habits.list_goals(session, user.id)
    own_habits = await habits.list_habits(session, user.id)
    weather = await _today_weather(session, user, tools, now)
    flags = (
        WeatherFlags(
            min_temp_c=weather.min_temp_c,
            max_temp_c=weather.max_temp_c,
            rain=weather.rain,
            frost=weather.frost,
            strong_wind=weather.strong_wind,
        )
        if weather
        else None
    )
    conditions = DayConditions(
        goals=goals,
        weather=flags,
        wants_outdoor=parsed.wants_outdoor,
        max_duration_min=max_duration(parsed),
        exclude_ids=frozenset(await quests.excluded_template_ids(session, user.id, day)),
    )
    candidates = select_candidates(
        await quests.active_templates(session), conditions, seed=f"{user.id}:{day}"
    )
    needs_rest = body.mood == "tired" or parsed.feels_unwell

    ranked = None
    left = POOL_DEADLINE_S - (time.monotonic() - started)
    if len(candidates) >= 5 and left > 1:
        profile = assistant.Profile(
            goals=goals,
            want_more=[h.text for h in own_habits if h.direction == "more"],
            want_less=[h.text for h in own_habits if h.direction == "less"],
            mood="tired" if needs_rest else body.mood,
            weather={
                "temperature_c": weather.temperature_c,
                "condition": weather.condition,
                "rain": weather.rain,
                "frost": weather.frost,
            }
            if weather
            else None,
        )
        ranked = await assistant.rank_pool(
            tools.assistant,
            profile,
            [
                assistant.Candidate(c.id, c.title, c.category, c.duration_min, c.outdoor)
                for c in candidates
            ],
            [t.title for t in parsed.tasks],
            needs_rest,
            deadline_s=left,
        )

    by_id = {c.id: c for c in candidates}
    if ranked is not None:
        picks = [(by_id[item.id], item.why) for item in ranked.value.items]
    else:
        picks = [
            (by_id[i], CODE_WHY.get(by_id[i].category)) for i in code_rank(candidates, needs_rest)
        ]

    new_quests = [
        NewQuest(
            source="checkin_task",
            title=t.title,
            category=t.category,
            duration_min=t.duration_min,
            why=TASK_WHY,
        )
        for t in parsed.tasks[:MAX_TASK_QUESTS]
    ] + [quests.quest_from_template(t, why) for t, why in picks]

    try:
        checkin, replaced = await quests.save_checkin(
            session, user.id, day, text, body.mood, parsed.model_dump(), now
        )
    except DayError as exc:
        raise day_problem(exc) from None
    pool = await quests.ensure_pool(session, user.id, day, now)
    await quests.rebuild_pool(
        session,
        pool,
        checkin,
        new_quests,
        ranked_by="llm" if ranked else "code",
        provider=ranked.provider if ranked else None,
        weather={
            "temperature_c": weather.temperature_c,
            "condition": weather.condition,
            "rain": weather.rain,
            "frost": weather.frost,
            "strong_wind": weather.strong_wind,
        }
        if weather
        else None,
        candidate_ids=[c.id for c in candidates],
        expires_at=day_clock.day_expires_at(day, user.timezone),
        now=now,
    )
    # Events carry counts and ids only; the check-in text never leaves the checkins table.
    await analytics.record(
        session,
        EventType.CHECKIN_SUBMITTED,
        user.id,
        {
            "checkin_id": checkin.id,
            "mood": body.mood,
            "empty": not text,
            "tasks": len(parsed.tasks),
            "parsed_by": parsed_by,
            "repeat": replaced,
        },
        occurred_at=now,
    )
    await analytics.record(
        session,
        EventType.POOL_SHOWN,
        user.id,
        {
            "pool_id": pool.id,
            "candidate_ids": [c.id for c in candidates],
            "shown_ids": [t.id for t, _ in picks],
            "tasks": min(len(parsed.tasks), MAX_TASK_QUESTS),
            "ranked_by": "llm" if ranked else "code",
            "provider": ranked.provider if ranked else "code",
            "weather": weather.condition if weather else "unknown",
        },
        occurred_at=now,
    )
    return await build_day(session, user, now)


# --- taking, replacing, own quests ---------------------------------------------------


def _taken_payload(quest: quests.DayQuest) -> dict[str, object]:
    return {
        "day_quest_id": quest.id,
        "template_id": quest.template_id,
        "source": quest.source,
        "category": quest.category,
        "position": quest.position,
    }


async def take_quest(
    session: AsyncSession, user: auth.User, quest_id: uuid.UUID, now: datetime
) -> DayQuest:
    day = day_clock.local_day(now, user.timezone)
    try:
        quest = await quests.take_quest(session, user.id, quest_id, day, now)
    except DayError as exc:
        raise day_problem(exc) from None
    await analytics.record(
        session, EventType.QUEST_TAKEN, user.id, _taken_payload(quest), occurred_at=now
    )
    return quest_schema(quest)


async def add_own_quest(
    session: AsyncSession, user: auth.User, body: OwnQuestInput, now: datetime
) -> DayQuest:
    day = day_clock.local_day(now, user.timezone)
    new = NewQuest(
        source="custom", title=body.title, category=body.category, duration_min=body.duration_min
    )
    try:
        quest = await quests.add_own_quest(
            session, user.id, day, new, day_clock.day_expires_at(day, user.timezone), now
        )
    except DayError as exc:
        raise day_problem(exc) from None
    await analytics.record(
        session, EventType.QUEST_TAKEN, user.id, _taken_payload(quest), occurred_at=now
    )
    return quest_schema(quest)


async def replace_quest(
    session: AsyncSession,
    user: auth.User,
    quest_id: uuid.UUID,
    reason: str | None,
    now: datetime,
) -> Replacement:
    day = day_clock.local_day(now, user.timezone)
    try:
        replaced, replacement, pool = await quests.replace_quest(
            session, user.id, quest_id, reason, day, now
        )
    except DayError as exc:
        raise day_problem(exc) from None
    await analytics.record(
        session,
        EventType.QUEST_REJECTED,
        user.id,
        {
            "day_quest_id": replaced.id,
            "template_id": replaced.template_id,
            "source": replaced.source,
            "category": replaced.category,
            "reason": reason,
            "replacement_id": replacement.id if replacement else None,
            "replacement_template_id": replacement.template_id if replacement else None,
        },
        occurred_at=now,
    )
    return Replacement(
        replaced=quest_schema(replaced),
        replacement=quest_schema(replacement) if replacement else None,
        replacements_left=quests.replacements_left(pool),
    )


async def complete_quest(
    session: AsyncSession,
    realtime: Realtime,
    user: auth.User,
    quest_id: uuid.UUID,
    body: CompleteQuestInput,
    now: datetime,
) -> Completion:
    """Visibility `friends` needs 1-3 photos and posts a proof; `routine` posts the fact
    without details; `personal` posts nothing. Points stay even if the post is deleted.
    In a co-op, the last one to complete brings everyone the bonus (committed here, then
    published)."""
    if body.visibility == "friends" and not body.media_ids:
        raise Problem(422, "photo-required", detail="Для друзей нужно хотя бы одно фото")
    if body.visibility != "friends" and (body.media_ids or body.caption):
        raise Problem(
            422, "validation-failed", detail="Фото и подпись только для видимости «друзья»"
        )
    if len(set(body.media_ids)) != len(body.media_ids):
        raise Problem(422, "validation-failed", detail="Фото повторяются")
    try:
        quest, award = await quests.complete_quest(session, user.id, quest_id, body.visibility, now)
    except DayError as exc:
        raise day_problem(exc) from None

    post_id: uuid.UUID | None = None
    if body.visibility != "personal":
        kind = "proof" if body.visibility == "friends" else "routine"
        try:
            post, to_process = await social.create_post(
                session,
                author_id=user.id,
                day_quest_id=quest.id,
                kind=kind,
                quest_title=quest.title,
                category=quest.category,
                caption=body.caption.strip() if body.caption else None,
                local_date=quest.local_date,
                media_ids=body.media_ids,
                now=now,
            )
        except social.MediaError:
            raise Problem(
                422, "invalid-media", detail="Фото не найдено или уже использовано"
            ) from None
        for media_id in to_process:
            await jobs.enqueue(session, social.PROCESS_JOB, {"media_id": str(media_id)})
        post_id = post.id
        await analytics.record(
            session,
            EventType.PROOF_POSTED,
            user.id,
            {
                "post_id": post.id,
                "day_quest_id": quest.id,
                "kind": kind,
                "photos": len(body.media_ids),
            },
            occurred_at=now,
        )
    await analytics.record(
        session,
        EventType.QUEST_COMPLETED,
        user.id,
        {
            "day_quest_id": quest.id,
            "template_id": quest.template_id,
            "source": quest.source,
            "category": quest.category,
            "visibility": body.visibility,
            "points": award.points,
            "streak_days": award.streak.current_days,
        },
        occurred_at=now,
    )
    in_coop = await quests.coop.after_completion(session, quest, now)
    bonus = 0
    if in_coop is not None:
        coop, bonuses = in_coop
        bonus = bonuses.get(quest.id, 0)
        await record_bonuses(session, coop, bonuses, user.id, now)
    await session.commit()
    if in_coop is not None:
        await publish(session, realtime, COOP_UPDATED, {"coop_id": str(in_coop[0].id)})
    return Completion(
        quest=quest_schema(
            quest, award.points + bonus, in_coop[0].id if in_coop is not None else None
        ),
        points_awarded=award.points,
        points_breakdown=PointsBreakdown(
            base=award.base,
            visibility_multiplier=award.visibility_multiplier,
            streak_multiplier=award.streak_multiplier,
        ),
        streak=streak_schema(award.streak),
        post_id=post_id,
        coop_bonus=bonus,
    )
