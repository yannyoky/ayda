"""User goals (from a catalog in code) and own habits worded by the user."""

from ayda.modules.habits.erase import erase_user
from ayda.modules.habits.goals import GOAL_CODES, GOALS, MAX_GOALS, Goal
from ayda.modules.habits.models import UserHabit
from ayda.modules.habits.service import (
    MAX_HABITS,
    Direction,
    GoalsError,
    HabitLimitError,
    add_habit,
    delete_habit,
    list_goals,
    list_habits,
    set_goals,
)

__all__ = [
    "GOALS",
    "GOAL_CODES",
    "MAX_GOALS",
    "MAX_HABITS",
    "Direction",
    "Goal",
    "GoalsError",
    "HabitLimitError",
    "UserHabit",
    "add_habit",
    "delete_habit",
    "erase_user",
    "list_goals",
    "list_habits",
    "set_goals",
]
