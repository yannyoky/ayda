from datetime import UTC, date, datetime
from typing import Any

import pytest

from ayda.app.day import guess_category, max_duration, parse_without_llm
from ayda.modules.assistant import ParsedCheckin
from ayda.modules.quests import Template
from ayda.modules.quests.days import day_expires_at, local_day, week_start
from ayda.modules.quests.scoring import ScoringConfig, base_points, quest_points, streak_multiplier
from ayda.modules.quests.selection import (
    DayConditions,
    WeatherFlags,
    code_rank,
    pick_alternative,
    select_candidates,
    weather_allows,
)

TZ = "Europe/Kaliningrad"  # UTC+2


def template(
    id: int,
    category: str = "sport",
    duration: int = 30,
    outdoor: bool = False,
    weather: dict[str, Any] | None = None,
    goals: list[str] | None = None,
) -> Template:
    return Template(
        id=id,
        slug=f"q-{id}",
        title=f"Квест {id}",
        description="",
        category=category,
        duration_min=duration,
        outdoor=outdoor,
        weather=weather or {},
        tags=[],
        goal_codes=goals or [],
        active=True,
    )


CLEAR = WeatherFlags(min_temp_c=8, max_temp_c=14, rain=False, frost=False, strong_wind=False)
RAIN = WeatherFlags(min_temp_c=8, max_temp_c=14, rain=True, frost=False, strong_wind=False)
FROST = WeatherFlags(min_temp_c=-20, max_temp_c=-16, rain=False, frost=True, strong_wind=False)
WIND = WeatherFlags(min_temp_c=8, max_temp_c=14, rain=False, frost=False, strong_wind=True)


@pytest.mark.parametrize(
    ("quest", "weather", "wants_outdoor", "allowed"),
    [
        (template(1, outdoor=True, duration=60), None, False, True),
        (template(1, outdoor=True, duration=60), CLEAR, False, True),
        (template(1, outdoor=True, duration=60), RAIN, False, False),
        (template(1, outdoor=True, duration=60), RAIN, True, True),
        (template(1, outdoor=True, duration=60), FROST, False, False),
        (template(1, outdoor=True, duration=15), RAIN, False, True),
        (template(1, outdoor=False, duration=90), RAIN, False, True),
        (template(1, outdoor=True, duration=15, weather={"no_rain": True}), RAIN, True, False),
        (template(1, outdoor=True, weather={"no_wind": True}), WIND, False, False),
        (template(1, outdoor=True, weather={"min_temp_c": 10}), CLEAR, False, False),
        (template(1, outdoor=True, weather={"max_temp_c": 2}), CLEAR, False, False),
        (template(1, outdoor=True, weather={"min_temp_c": 5}), CLEAR, False, True),
    ],
)
def test_weather_rules(
    quest: Template, weather: WeatherFlags | None, wants_outdoor: bool, allowed: bool
) -> None:
    assert weather_allows(quest, weather, wants_outdoor) is allowed


def conditions(**overrides: Any) -> DayConditions:
    values: dict[str, Any] = {
        "goals": [],
        "weather": None,
        "wants_outdoor": False,
        "max_duration_min": 480,
        "exclude_ids": frozenset(),
    }
    return DayConditions(**(values | overrides))


def test_candidates_respect_exclusions_duration_and_category_cap() -> None:
    templates = [template(i, "sport", 30) for i in range(1, 11)] + [
        template(100, "rest", 120),
        template(101, "rest", 20),
        template(102, "walk", 30, goals=["more_movement"]),
    ]

    picked = select_candidates(
        templates,
        conditions(goals=["more_movement"], max_duration_min=60, exclude_ids=frozenset({1})),
        seed="u:2026-10-16",
    )

    ids = [t.id for t in picked]
    assert ids[0] == 102  # matches a goal
    assert 1 not in ids and 100 not in ids
    assert sum(t.category == "sport" for t in picked) == 5
    assert select_candidates(templates, conditions(), "same") == select_candidates(
        templates, conditions(), "same"
    )


def test_code_rank_puts_rest_first_for_tired_and_keeps_variety() -> None:
    candidates = [template(i, "sport") for i in range(1, 6)] + [
        template(10, "walk"),
        template(11, "rest"),
        template(12, "home"),
    ]

    tired = code_rank(candidates, needs_rest=True)
    normal = code_rank(candidates, needs_rest=False)

    assert tired[0] == 11
    assert len(tired) == len(normal) == 6
    assert normal[:2] == [1, 2] and 3 not in normal[:4]


def test_code_rank_fills_up_when_categories_run_out() -> None:
    assert code_rank([template(i, "sport") for i in range(1, 9)], False) == [1, 2, 3, 4, 5, 6]


def test_alternative_prefers_other_category_then_duration() -> None:
    same = [template(1, "sport", 30), template(2, "sport", 15), template(3, "walk", 30)]
    assert pick_alternative(same, "sport", 30) == same[2]
    assert pick_alternative(same[:2], "sport", 30) == same[1]
    assert pick_alternative(same[:1], "sport", 30) is None


def test_checkin_without_llm_turns_lines_into_tasks() -> None:
    parsed = parse_without_llm("- Сдать отчёт до 15:00\n\n  сходить в зал\nпозвонить маме\n")

    assert [t.title for t in parsed.tasks] == [
        "Сдать отчёт до 15:00",
        "сходить в зал",
        "позвонить маме",
    ]
    assert [t.category for t in parsed.tasks] == ["project", "sport", "social"]
    assert parsed.tasks[0].at == "15:00"
    assert parsed.free_evening
    assert parse_without_llm("").tasks == []
    assert guess_category("Прочитать главу книги") == "learning"


def test_busy_day_limits_quest_length() -> None:
    free = ParsedCheckin(tasks=[], busy=[], free_evening=True)
    busy = ParsedCheckin(tasks=[], busy=["09:00-18:00", "19:00-22:30"], free_evening=False)

    assert max_duration(free) == 480
    assert max_duration(busy) == 60
    assert max_duration(busy.model_copy(update={"free_evening": True})) == 150


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2026, 10, 16, 1, 59, tzinfo=UTC), date(2026, 10, 15)),  # 03:59 local
        (datetime(2026, 10, 16, 2, 0, tzinfo=UTC), date(2026, 10, 16)),  # 04:00 local
        (datetime(2026, 10, 16, 21, 30, tzinfo=UTC), date(2026, 10, 16)),  # 23:30 local
    ],
)
def test_local_day_starts_at_four(utc: datetime, expected: date) -> None:
    assert local_day(utc, TZ) == expected


def test_day_expiry_and_week_start() -> None:
    assert day_expires_at(date(2026, 10, 16), TZ) == datetime(2026, 10, 17, 2, 0, tzinfo=UTC)
    assert week_start(date(2026, 10, 18)) == date(2026, 10, 12)  # Sunday -> Monday


@pytest.mark.parametrize(
    ("duration", "points"), [(5, 10), (15, 10), (16, 20), (30, 20), (45, 35), (60, 35), (90, 50)]
)
def test_base_points_by_duration(duration: int, points: int) -> None:
    assert base_points(duration, ScoringConfig()) == points


@pytest.mark.parametrize(
    ("days", "multiplier"), [(0, 1.0), (6, 1.0), (7, 1.1), (14, 1.2), (21, 1.3), (70, 1.3)]
)
def test_streak_multiplier(days: int, multiplier: float) -> None:
    assert streak_multiplier(days, ScoringConfig()) == multiplier


@pytest.mark.parametrize(
    ("duration", "visibility", "streak", "points"),
    [
        (30, "friends", 0, 20),
        (30, "routine", 0, 15),
        (30, "personal", 0, 10),
        (60, "friends", 7, 39),  # 35 * 1.1 = 38.5 rounds half up
        (90, "routine", 21, 49),  # 50 * 0.75 * 1.3 = 48.75
    ],
)
def test_quest_points(duration: int, visibility: str, streak: int, points: int) -> None:
    assert quest_points(duration, visibility, streak, ScoringConfig())[0] == points
