"""chat.attachments: voice messages (ADR 0019); a voice message has empty text

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat.messages DROP CONSTRAINT messages_text_check")
    op.execute(
        """
        CREATE TABLE chat.attachments (
            id uuid PRIMARY KEY,
            conversation_id uuid NOT NULL REFERENCES chat.conversations (id) ON DELETE CASCADE,
            owner_id uuid NOT NULL,
            message_id bigint UNIQUE REFERENCES chat.messages (id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('voice')),
            status text NOT NULL CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
            storage_key text NOT NULL,
            content_type text NOT NULL,
            size_bytes integer NOT NULL,
            duration_ms integer,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_attachments_owner_id_created_at ON chat.attachments (owner_id, created_at)"
    )
    op.execute("CREATE INDEX ix_attachments_conversation_id ON chat.attachments (conversation_id)")


def downgrade() -> None:
    op.execute("DROP TABLE chat.attachments")
    op.execute(
        "ALTER TABLE chat.messages ADD CONSTRAINT messages_text_check "
        "CHECK (length(text) >= 1) NOT VALID"
    )
