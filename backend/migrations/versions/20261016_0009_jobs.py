"""jobs.jobs: background job queue in PostgreSQL

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS jobs")
    op.execute(
        """
        CREATE TABLE jobs.jobs (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            kind text NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            dedupe_key text,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'failed')),
            run_at timestamptz NOT NULL DEFAULT now(),
            attempts smallint NOT NULL DEFAULT 0,
            max_attempts smallint NOT NULL DEFAULT 5,
            locked_at timestamptz,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            CONSTRAINT uq_jobs_dedupe_key UNIQUE (dedupe_key)
        )
        """
    )
    op.execute("CREATE INDEX ix_jobs_queued_run_at ON jobs.jobs (run_at) WHERE status = 'queued'")
    op.execute("CREATE INDEX ix_jobs_finished_at ON jobs.jobs (finished_at)")


def downgrade() -> None:
    op.execute("DROP SCHEMA jobs CASCADE")
