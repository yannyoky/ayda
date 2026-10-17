"""Candidate selection and the code-only ranking. Code decides what is allowed; the LLM only
orders and phrases what passes here."""

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ayda.modules.quests.models import Template

MAX_CANDIDATES = 30
MAX_PER_CATEGORY = 5
POOL_SIZE = 6
MAX_PER_CATEGORY_IN_POOL = 2
LONG_OUTDOOR_MIN = 30
# A quest whose own minimum is above this needs warm weather (a picnic).
NEEDS_WARMTH_C = 5

# One "why you" line per category for the code-only ranking.
CODE_WHY = {
    "sport": "Немного движения сегодня точно пойдёт на пользу.",
    "walk": "Свежий воздух и шаги без лишних усилий.",
    "city": "Повод увидеть свой город по-новому.",
    "rest": "Отдых тоже считается: восстанови силы.",
    "project": "Шаг к своему делу, пока есть время.",
    "social": "Хороший повод побыть с людьми.",
    "home": "Небольшое дело, после которого дома станет лучше.",
    "learning": "Немного нового знания в копилку.",
}


@dataclass(frozen=True)
class WeatherFlags:
    """What quest selection needs from today's weather (rest of the local day)."""

    min_temp_c: float
    max_temp_c: float
    rain: bool
    frost: bool
    strong_wind: bool
    storm: bool = False


@dataclass(frozen=True)
class DayConditions:
    goals: Sequence[str]
    weather: WeatherFlags | None
    wants_outdoor: bool
    max_duration_min: int
    exclude_ids: frozenset[int]
    feels_unwell: bool = False


def weather_allows(
    template: Template,
    weather: WeatherFlags | None,
    wants_outdoor: bool,
    feels_unwell: bool = False,
) -> bool:
    """Hard limits first: a storm, the quest's own weather rule, hard frost and feeling unwell
    are never lifted. An explicit wish to be outside lifts only the general rain rule."""
    if not template.outdoor:
        return True
    long_outdoor = template.duration_min >= LONG_OUTDOOR_MIN
    if feels_unwell and long_outdoor:
        return False
    rule = template.weather
    if weather is None:
        # Unknown weather: skip quests that only make sense in particular weather
        # (snow and ice need frost, a picnic needs warmth).
        min_temp = rule.get("min_temp_c")
        return "max_temp_c" not in rule and not (
            isinstance(min_temp, int | float) and min_temp > NEEDS_WARMTH_C
        )
    if weather.storm:
        return False
    if rule.get("no_rain") and weather.rain:
        return False
    if rule.get("no_wind") and weather.strong_wind:
        return False
    min_temp = rule.get("min_temp_c")
    if isinstance(min_temp, int | float) and weather.min_temp_c < min_temp:
        return False
    max_temp = rule.get("max_temp_c")
    if isinstance(max_temp, int | float) and weather.max_temp_c > max_temp:
        return False
    if long_outdoor and weather.frost:
        return False
    # No long outdoor quests in rain unless the user asked to be outside anyway.
    return not (long_outdoor and weather.rain and not wants_outdoor)


def _score(template: Template, goals: Sequence[str], rng: random.Random) -> float:
    return 2.0 * len(set(template.goal_codes) & set(goals)) + rng.random()


def select_candidates(
    templates: Iterable[Template], conditions: DayConditions, seed: str
) -> list[Template]:
    """Up to 30 allowed quests, best first, at most 5 per category for variety."""
    rng = random.Random(seed)
    allowed = [
        t
        for t in templates
        if t.active
        and t.id not in conditions.exclude_ids
        and t.duration_min <= conditions.max_duration_min
        and weather_allows(t, conditions.weather, conditions.wants_outdoor, conditions.feels_unwell)
    ]
    scored = sorted(allowed, key=lambda t: (-_score(t, conditions.goals, rng), t.id))
    per_category: Counter[str] = Counter()
    picked: list[Template] = []
    for template in scored:
        if per_category[template.category] >= MAX_PER_CATEGORY:
            continue
        per_category[template.category] += 1
        picked.append(template)
        if len(picked) == MAX_CANDIDATES:
            break
    return picked


def code_rank(candidates: Sequence[Template], needs_rest: bool, size: int = POOL_SIZE) -> list[int]:
    """Fallback without the LLM: candidates are already best first; keep variety and put a
    rest quest first for a tired user."""
    picked: list[Template] = []
    if needs_rest:
        rest = next((c for c in candidates if c.category == "rest"), None)
        if rest is not None:
            picked.append(rest)
    per_category = Counter(c.category for c in picked)
    for candidate in candidates:
        if len(picked) == size:
            break
        if candidate in picked or per_category[candidate.category] >= MAX_PER_CATEGORY_IN_POOL:
            continue
        per_category[candidate.category] += 1
        picked.append(candidate)
    for candidate in candidates:  # too few categories: fill up regardless of variety
        if len(picked) == size:
            break
        if candidate not in picked:
            picked.append(candidate)
    return [c.id for c in picked]


def pick_alternative(
    candidates: Sequence[Template], replaced_category: str, replaced_duration: int
) -> Template | None:
    """A replacement from another category, else of another duration."""
    for candidate in candidates:
        if candidate.category != replaced_category:
            return candidate
    for candidate in candidates:
        if candidate.duration_min != replaced_duration:
            return candidate
    return None
