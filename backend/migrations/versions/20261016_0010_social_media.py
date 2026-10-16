"""social.media: uploaded photos

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # post_id becomes a foreign key to social.posts when posts arrive (#28).
    op.execute(
        """
        CREATE TABLE social.media (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL,
            post_id uuid,
            storage_key text NOT NULL,
            content_type text NOT NULL
                CHECK (content_type IN ('image/jpeg', 'image/png', 'image/heic', 'image/webp')),
            size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
            width smallint,
            height smallint,
            status text NOT NULL CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_media_owner_id_created_at ON social.media (owner_id, created_at)")
    op.execute("CREATE INDEX ix_media_post_id ON social.media (post_id)")


def downgrade() -> None:
    op.execute("DROP TABLE social.media")
