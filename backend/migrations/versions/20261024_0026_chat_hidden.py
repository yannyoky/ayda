"""chat.members.hidden_at: "Удалить у себя" for a chat

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat.members ADD COLUMN hidden_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE chat.members DROP COLUMN hidden_at")
