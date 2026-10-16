"""habits.user_goals and habits.user_habits

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.execute(
        """
        CREATE TABLE habits.user_habits (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL,
            direction text NOT NULL CONSTRAINT ck_user_habits_direction
                CHECK (direction IN ('more', 'less')),
            text varchar(100) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX ix_user_habits_user_id ON habits.user_habits (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE habits.user_habits")
    op.execute("DROP TABLE habits.user_goals")
