"""analytics.events: append-only product events

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE analytics.events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            user_id uuid,
            type text NOT NULL,
            schema_version smallint NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute("CREATE INDEX ix_events_type_occurred_at ON analytics.events (type, occurred_at)")
    op.execute(
        "CREATE INDEX ix_events_user_id_occurred_at ON analytics.events (user_id, occurred_at)"
    )
    # Append-only: UPDATE and DELETE fail unless the transaction opts in with
    # SET LOCAL ayda.analytics_maintenance = 'on' (account anonymization only).
    op.execute(
        """
        CREATE FUNCTION analytics.forbid_event_changes() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF coalesce(current_setting('ayda.analytics_maintenance', true), '') <> 'on' THEN
                RAISE EXCEPTION 'analytics.events is append-only';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON analytics.events
        FOR EACH ROW EXECUTE FUNCTION analytics.forbid_event_changes()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE analytics.events")
    op.execute("DROP FUNCTION analytics.forbid_event_changes()")
