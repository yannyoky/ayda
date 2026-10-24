"""habits.user_interests and user_interest_tags replace user_goals (ADR 0018)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Each old goal becomes the interests it served; quest templates move the same way.
GOAL_TO_INTERESTS = {
    "more_movement": ["sport", "outdoors"],
    "less_screen": ["friends", "outdoors"],
    "better_sleep": ["rest"],
    "own_project": ["project"],
    "see_friends": ["friends", "games"],
    "explore_city": ["city", "outdoors"],
    "learn": ["learning", "books"],
    "rest_well": ["rest"],
    "calm_mind": ["rest", "outdoors"],
    "home_order": ["home"],
}
INTEREST_TO_GOAL = {
    "sport": "more_movement",
    "outdoors": "more_movement",
    "city": "explore_city",
    "learning": "learn",
    "books": "learn",
    "rest": "rest_well",
    "project": "own_project",
    "friends": "see_friends",
    "games": "see_friends",
    "home": "home_order",
}


def _interests(codes: list[str]) -> list[str]:
    """Goals become their interests; codes that already are interests (a fresh database gets
    the current catalog in 0006) stay."""
    out: list[str] = []
    for goal in codes:
        for code in GOAL_TO_INTERESTS.get(goal, [goal]):
            if code not in out:
                out.append(code)
    return out


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        """
        CREATE TABLE habits.user_interests (
            user_id uuid NOT NULL,
            code text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE habits.user_interest_tags (
            user_id uuid NOT NULL,
            tag varchar(30) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, tag)
        )
        """
    )
    rows = bind.execute(sa.text("SELECT user_id, goal_code, created_at FROM habits.user_goals"))
    seen: set[tuple[object, str]] = set()
    for user_id, goal, created_at in rows.fetchall():
        for code in GOAL_TO_INTERESTS.get(goal, []):
            if (user_id, code) in seen:
                continue
            seen.add((user_id, code))
            bind.execute(
                sa.text(
                    "INSERT INTO habits.user_interests (user_id, code, created_at)"
                    " VALUES (:u, :c, :t)"
                ),
                {"u": user_id, "c": code, "t": created_at},
            )
    op.execute("DROP TABLE habits.user_goals")

    op.execute("ALTER TABLE quests.templates RENAME COLUMN goal_codes TO interest_codes")
    templates = bind.execute(sa.text("SELECT id, interest_codes FROM quests.templates"))
    for template_id, goals in templates.fetchall():
        bind.execute(
            sa.text("UPDATE quests.templates SET interest_codes = :c WHERE id = :i"),
            {"c": _interests(list(goals or [])), "i": template_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(
        """
        CREATE TABLE habits.user_goals (
            user_id uuid NOT NULL,
            goal_code text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, goal_code)
        )
        """
    )
    rows = bind.execute(sa.text("SELECT user_id, code, created_at FROM habits.user_interests"))
    seen: set[tuple[object, str]] = set()
    for user_id, code, created_at in rows.fetchall():
        goal = INTEREST_TO_GOAL.get(code)
        if goal is None or (user_id, goal) in seen:
            continue
        seen.add((user_id, goal))
        bind.execute(
            sa.text(
                "INSERT INTO habits.user_goals (user_id, goal_code, created_at) VALUES (:u, :c, :t)"
            ),
            {"u": user_id, "c": goal, "t": created_at},
        )
    op.execute("DROP TABLE habits.user_interest_tags")
    op.execute("DROP TABLE habits.user_interests")
    op.execute("ALTER TABLE quests.templates RENAME COLUMN interest_codes TO goal_codes")
    templates = bind.execute(sa.text("SELECT id, goal_codes FROM quests.templates"))
    for template_id, codes in templates.fetchall():
        goals = list(
            dict.fromkeys(INTEREST_TO_GOAL[c] for c in codes or [] if c in INTEREST_TO_GOAL)
        )
        bind.execute(
            sa.text("UPDATE quests.templates SET goal_codes = :g WHERE id = :i"),
            {"g": goals, "i": template_id},
        )
