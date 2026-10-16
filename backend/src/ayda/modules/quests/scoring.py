"""Points rules (docs/prd.md "Quests, points, streaks and ladder"). Only the backend computes them.

The coefficients are configuration: defaults below, overridable with the SCORING_CONFIG
environment variable (JSON with the same keys) without a code change.
"""

import json
import os
from dataclasses import dataclass, field
from functools import cache


@dataclass(frozen=True)
class ScoringConfig:
    version: int = 1
    # (max duration in minutes, base points); the last bucket covers everything longer
    base_buckets: tuple[tuple[int, int], ...] = ((15, 10), (30, 20), (60, 35), (10_000, 50))
    visibility: dict[str, float] = field(
        default_factory=lambda: {"friends": 1.0, "routine": 0.75, "personal": 0.5}
    )
    streak_step_days: int = 7
    streak_step_bonus: float = 0.1
    streak_max_bonus: float = 0.3
    max_taken_per_day: int = 3
    max_replacements_per_day: int = 5
    # Each participant of a co-op quest gets this share of their quest points once all
    # who joined have completed it.
    coop_bonus_share: float = 0.5
    max_coop_friends: int = 3


@cache
def scoring_config() -> ScoringConfig:
    raw = os.environ.get("SCORING_CONFIG")
    if not raw:
        return ScoringConfig()
    data = json.loads(raw)
    if "base_buckets" in data:
        data["base_buckets"] = tuple(tuple(b) for b in data["base_buckets"])
    return ScoringConfig(**data)


def base_points(duration_min: int, config: ScoringConfig | None = None) -> int:
    config = config or scoring_config()
    for max_minutes, points in config.base_buckets:
        if duration_min <= max_minutes:
            return points
    return config.base_buckets[-1][1]


def streak_multiplier(streak_days: int, config: ScoringConfig | None = None) -> float:
    config = config or scoring_config()
    steps = streak_days // config.streak_step_days
    return round(1 + min(steps * config.streak_step_bonus, config.streak_max_bonus), 4)


def quest_points(
    duration_min: int, visibility: str, streak_days: int, config: ScoringConfig | None = None
) -> tuple[int, int, float, float]:
    """(points, base, visibility multiplier, streak multiplier); rounded half up."""
    config = config or scoring_config()
    base = base_points(duration_min, config)
    vis = config.visibility[visibility]
    streak = streak_multiplier(streak_days, config)
    return int(base * vis * streak + 0.5), base, vis, streak
