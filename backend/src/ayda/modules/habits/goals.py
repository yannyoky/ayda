from dataclasses import dataclass


@dataclass(frozen=True)
class Goal:
    code: str
    title: str


# Goal catalog (codes are stable; quest templates refer to them in `goal_codes`).
GOALS: tuple[Goal, ...] = (
    Goal("more_movement", "Больше двигаться"),
    Goal("less_screen", "Меньше сидеть в телефоне и играх"),
    Goal("better_sleep", "Высыпаться"),
    Goal("own_project", "Двигать свой проект"),
    Goal("see_friends", "Чаще видеться с людьми"),
    Goal("explore_city", "Узнавать свой город"),
    Goal("learn", "Учиться новому"),
    Goal("rest_well", "Отдыхать без чувства вины"),
    Goal("calm_mind", "Меньше стресса"),
    Goal("home_order", "Порядок дома и в делах"),
)

GOAL_CODES = frozenset(g.code for g in GOALS)
MAX_GOALS = 5
