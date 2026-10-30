"""auth.users.sessions_revoked_at: "sign out everywhere" (audit V5)

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE auth.users ADD COLUMN sessions_revoked_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE auth.users DROP COLUMN sessions_revoked_at")
