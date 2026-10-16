"""assistant.llm_calls: LLM call metadata without prompt or answer text

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE assistant.llm_calls (
            id uuid PRIMARY KEY,
            purpose text NOT NULL,
            provider text NOT NULL,
            model text NOT NULL,
            latency_ms integer NOT NULL,
            ok boolean NOT NULL,
            error_kind text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_llm_calls_created_at ON assistant.llm_calls (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE assistant.llm_calls")
