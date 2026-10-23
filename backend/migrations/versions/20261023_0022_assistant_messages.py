"""assistant.messages: the day chat with the assistant (M6, ADR 0013)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE assistant.messages (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            local_date date NOT NULL,
            quest_id uuid,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            text text NOT NULL,
            source text CHECK (source IN ('llm', 'code')),
            cards jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_messages_user_id_local_date ON assistant.messages (user_id, local_date)"
    )
    op.execute("CREATE INDEX ix_messages_local_date ON assistant.messages (local_date)")


def downgrade() -> None:
    op.execute("DROP TABLE assistant.messages")
