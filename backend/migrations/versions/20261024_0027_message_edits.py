"""chat.messages.edited_at: the author edited the message (ADR 0019)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat.messages ADD COLUMN edited_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE chat.messages DROP COLUMN edited_at")
