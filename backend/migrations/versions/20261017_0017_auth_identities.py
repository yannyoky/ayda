"""auth.identities, email sign-in codes and refresh tokens (M4, ADR 0009)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE auth.users ALTER COLUMN telegram_id DROP NOT NULL")
    op.execute(
        """
        CREATE TABLE auth.identities (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            provider text NOT NULL CONSTRAINT ck_identities_provider
                CHECK (provider IN ('telegram', 'email')),
            subject text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_identities_provider_subject UNIQUE (provider, subject)
        )
        """
    )
    op.execute("CREATE INDEX ix_identities_user_id ON auth.identities (user_id)")
    op.execute(
        """
        INSERT INTO auth.identities (id, user_id, provider, subject, created_at)
        SELECT gen_random_uuid(), id, 'telegram', telegram_id::text, created_at
        FROM auth.users WHERE telegram_id IS NOT NULL
        """
    )
    # One live code per email; keys are HMACs, so no address is stored before sign-in.
    op.execute(
        """
        CREATE TABLE auth.email_codes (
            email_key bytea PRIMARY KEY,
            code_hash bytea NOT NULL,
            attempts integer NOT NULL DEFAULT 0,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE auth.email_sends (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            email_key bytea NOT NULL,
            client_key bytea NOT NULL,
            sent_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_email_sends_email_key ON auth.email_sends (email_key, sent_at)")
    op.execute("CREATE INDEX ix_email_sends_client_key ON auth.email_sends (client_key, sent_at)")
    op.execute(
        """
        CREATE TABLE auth.refresh_tokens (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            family_id uuid NOT NULL,
            token_hash bytea NOT NULL CONSTRAINT uq_refresh_tokens_token_hash UNIQUE,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_refresh_tokens_family_id ON auth.refresh_tokens (family_id)")
    op.execute("CREATE INDEX ix_refresh_tokens_user_id ON auth.refresh_tokens (user_id)")


def downgrade() -> None:
    # Refuse rather than delete accounts that can only sign in by email.
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM auth.users WHERE telegram_id IS NULL) THEN
                RAISE EXCEPTION 'users without Telegram exist; erase them before downgrading';
            END IF;
        END $$
        """
    )
    op.execute("DROP TABLE auth.refresh_tokens")
    op.execute("DROP TABLE auth.email_sends")
    op.execute("DROP TABLE auth.email_codes")
    op.execute("DROP TABLE auth.identities")
    op.execute("ALTER TABLE auth.users ALTER COLUMN telegram_id SET NOT NULL")
