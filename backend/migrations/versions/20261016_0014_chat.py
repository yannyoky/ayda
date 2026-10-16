"""chat.conversations, chat.members, chat.messages (M2, US-17)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE chat.conversations (
            id uuid PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN ('dm', 'coop')),
            -- 'dm': the two member ids, ordered, so a pair has one chat
            dm_key text UNIQUE,
            coop_id uuid UNIQUE,
            created_at timestamptz NOT NULL,
            last_message_at timestamptz,
            CHECK ((kind = 'dm') = (dm_key IS NOT NULL)),
            CHECK ((kind = 'coop') = (coop_id IS NOT NULL))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE chat.members (
            conversation_id uuid NOT NULL REFERENCES chat.conversations (id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            last_read_message_id bigint,
            joined_at timestamptz NOT NULL,
            PRIMARY KEY (conversation_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_members_user_id ON chat.members (user_id)")
    op.execute(
        """
        CREATE TABLE chat.messages (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            conversation_id uuid NOT NULL REFERENCES chat.conversations (id) ON DELETE CASCADE,
            author_id uuid NOT NULL,
            client_id uuid,
            text varchar(2000) NOT NULL CHECK (length(text) >= 1),
            created_at timestamptz NOT NULL,
            deleted_at timestamptz,
            UNIQUE (author_id, client_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_messages_conversation_id_id ON chat.messages (conversation_id, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_messages_author_id_created_at ON chat.messages (author_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE chat.messages")
    op.execute("DROP TABLE chat.members")
    op.execute("DROP TABLE chat.conversations")
