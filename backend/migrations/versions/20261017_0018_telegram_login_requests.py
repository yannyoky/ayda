"""auth.telegram_login_requests: sign-in through the bot from native apps (ADR 0009)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth.telegram_login_requests (
            id uuid PRIMARY KEY,
            code_hash bytea NOT NULL CONSTRAINT uq_telegram_login_requests_code_hash UNIQUE,
            secret_hash bytea NOT NULL,
            client_key bytea NOT NULL,
            link_user_id uuid REFERENCES auth.users (id) ON DELETE CASCADE,
            status text NOT NULL DEFAULT 'pending' CONSTRAINT ck_telegram_login_requests_status
                CHECK (status IN ('pending', 'approved', 'used')),
            telegram_id bigint,
            first_name text,
            last_name text,
            username text,
            expires_at timestamptz NOT NULL,
            approved_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_telegram_login_requests_client_key"
        " ON auth.telegram_login_requests (client_key, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE auth.telegram_login_requests")
