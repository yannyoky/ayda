"""Problem codes for the rules of the day and co-op quests (quests.DayError codes)."""

from ayda.core.problems import Problem
from ayda.modules.quests.day_service import DayError

PROBLEMS: dict[str, tuple[int, str]] = {
    "quest-not-found": (404, "Такого квеста сегодня нет"),
    "quest-not-offered": (409, "Этот квест уже не предлагается"),
    "daily-limit-reached": (409, "Сегодня уже взято 3 квеста"),
    "no-replacements-left": (409, "Замены на сегодня закончились"),
    "too-many-checkins": (429, "Слишком много чек-инов за день"),
    "quest-not-taken": (409, "Сначала возьми этот квест"),
    "quest-already-completed": (409, "Квест уже выполнен"),
    "quest-expired": (409, "День этого квеста уже закончился"),
    "quest-already-coop": (409, "Этот квест уже совместный"),
    "coop-not-found": (404, "Совместный квест не найден"),
    "coop-already-answered": (409, "Ты уже ответил на это приглашение"),
    "coop-over": (410, "Этот совместный квест уже закончился"),
}


def day_problem(error: DayError) -> Problem:
    status, detail = PROBLEMS[error.code]
    return Problem(status, error.code, detail=detail)
