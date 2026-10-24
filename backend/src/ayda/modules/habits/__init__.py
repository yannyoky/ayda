"""User interests (a catalog in code plus own words) and own habits worded by the user."""

from ayda.modules.habits.erase import erase_user
from ayda.modules.habits.interests import (
    BY_CODE,
    INTEREST_CODES,
    INTERESTS,
    MAX_INTERESTS,
    MAX_TAG_LENGTH,
    MAX_TAGS,
    Interest,
    categories_of,
    words_of,
)
from ayda.modules.habits.models import UserHabit
from ayda.modules.habits.service import (
    MAX_HABITS,
    Direction,
    HabitLimitError,
    InterestsError,
    add_habit,
    delete_habit,
    list_habits,
    list_interests,
    list_tags,
    normalize_tag,
    set_interests,
)

__all__ = [
    "BY_CODE",
    "INTERESTS",
    "INTEREST_CODES",
    "MAX_HABITS",
    "MAX_INTERESTS",
    "MAX_TAGS",
    "MAX_TAG_LENGTH",
    "Direction",
    "HabitLimitError",
    "Interest",
    "InterestsError",
    "UserHabit",
    "add_habit",
    "categories_of",
    "delete_habit",
    "erase_user",
    "list_habits",
    "list_interests",
    "list_tags",
    "normalize_tag",
    "set_interests",
    "words_of",
]
