"""chat.attachments: video circles that expire after 30 days (ADR 0019)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat.attachments DROP CONSTRAINT attachments_kind_check")
    op.execute("ALTER TABLE chat.attachments DROP CONSTRAINT attachments_status_check")
    op.execute(
        "ALTER TABLE chat.attachments ADD CONSTRAINT attachments_kind_check "
        "CHECK (kind IN ('voice', 'video_note'))"
    )
    op.execute(
        "ALTER TABLE chat.attachments ADD CONSTRAINT attachments_status_check "
        "CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'expired'))"
    )
    op.execute(
        "CREATE INDEX ix_attachments_video_notes ON chat.attachments (created_at) "
        "WHERE kind = 'video_note' AND status <> 'expired'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX chat.ix_attachments_video_notes")
    op.execute("DELETE FROM chat.attachments WHERE kind = 'video_note'")
    op.execute("ALTER TABLE chat.attachments DROP CONSTRAINT attachments_kind_check")
    op.execute("ALTER TABLE chat.attachments DROP CONSTRAINT attachments_status_check")
    op.execute(
        "ALTER TABLE chat.attachments ADD CONSTRAINT attachments_kind_check "
        "CHECK (kind IN ('voice'))"
    )
    op.execute(
        "ALTER TABLE chat.attachments ADD CONSTRAINT attachments_status_check "
        "CHECK (status IN ('pending', 'processing', 'ready', 'failed'))"
    )
