"""social.likes, social.comments

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE social.likes (
            post_id uuid NOT NULL REFERENCES social.posts (id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (post_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE social.comments (
            id uuid PRIMARY KEY,
            post_id uuid NOT NULL REFERENCES social.posts (id) ON DELETE CASCADE,
            author_id uuid NOT NULL,
            text varchar(500) NOT NULL CHECK (length(text) >= 1),
            created_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_comments_post_id_created_at ON social.comments (post_id, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_comments_author_id_created_at ON social.comments (author_id, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_posts_created_at_id ON social.posts (created_at DESC, id DESC)"
        " WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX social.ix_posts_created_at_id")
    op.execute("DROP TABLE social.comments")
    op.execute("DROP TABLE social.likes")
