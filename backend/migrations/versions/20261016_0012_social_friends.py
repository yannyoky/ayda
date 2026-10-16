"""social.invites, social.friendships

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE social.invites (
            code text PRIMARY KEY CHECK (length(code) BETWEEN 10 AND 64),
            inviter_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_invites_inviter_id_created_at ON social.invites (inviter_id, created_at)"
    )
    op.execute(
        """
        CREATE TABLE social.friendships (
            user_low uuid NOT NULL,
            user_high uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_low, user_high),
            CONSTRAINT ck_friendships_ordered CHECK (user_low < user_high)
        )
        """
    )
    op.execute("CREATE INDEX ix_friendships_user_high ON social.friendships (user_high)")


def downgrade() -> None:
    op.execute("DROP TABLE social.friendships")
    op.execute("DROP TABLE social.invites")
