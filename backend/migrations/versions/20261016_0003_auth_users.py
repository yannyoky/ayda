"""auth.users and auth.consents

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth.users (
            id uuid PRIMARY KEY,
            telegram_id bigint NOT NULL,
            first_name text NOT NULL,
            last_name text,
            username text,
            avatar_url text,
            city_id integer,
            timezone text NOT NULL DEFAULT 'Europe/Moscow',
            theme text NOT NULL DEFAULT 'graphite' CONSTRAINT ck_users_theme
                CHECK (theme IN ('graphite', 'plum')),
            morning_reminder_at time,
            evening_reminder_at time,
            bot_reachable boolean NOT NULL DEFAULT true,
            onboarded_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            deletion_requested_at timestamptz,
            CONSTRAINT uq_users_telegram_id UNIQUE (telegram_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE auth.consents (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            version text NOT NULL,
            accepted_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_consents_user_id_version UNIQUE (user_id, version)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE auth.consents")
    op.execute("DROP TABLE auth.users")
