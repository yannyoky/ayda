"""auth.devices for push notifications and the user's notification channel (M4, ADR 0009)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE auth.users ADD COLUMN notification_channel text NOT NULL DEFAULT 'auto'
            CONSTRAINT ck_users_notification_channel
            CHECK (notification_channel IN ('auto', 'push', 'telegram'))
        """
    )
    op.execute(
        """
        CREATE TABLE auth.devices (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            platform text NOT NULL CONSTRAINT ck_devices_platform
                CHECK (platform IN ('android', 'ios')),
            token text NOT NULL CONSTRAINT uq_devices_token UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_devices_user_id ON auth.devices (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE auth.devices")
    op.execute("ALTER TABLE auth.users DROP COLUMN notification_channel")
