"""quests.checkins, quests.day_pools, quests.day_quests: the user's day

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "('sport', 'walk', 'city', 'rest', 'project', 'social', 'home', 'learning')"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quests.checkins (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL,
            local_date date NOT NULL,
            text varchar(1000),
            mood text NOT NULL CHECK (mood IN ('energetic', 'normal', 'tired')),
            parsed jsonb NOT NULL DEFAULT '{}'::jsonb,
            submissions smallint NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_checkins_user_id_local_date UNIQUE (user_id, local_date)
        )
        """
    )
    op.execute("CREATE INDEX ix_checkins_created_at ON quests.checkins (created_at)")
    op.execute(
        """
        CREATE TABLE quests.day_pools (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL,
            local_date date NOT NULL,
            checkin_id uuid REFERENCES quests.checkins (id) ON DELETE SET NULL,
            status text NOT NULL CHECK (status IN ('none', 'generating', 'ready', 'failed')),
            ranked_by text CHECK (ranked_by IN ('llm', 'code')),
            provider text,
            weather jsonb,
            context jsonb NOT NULL DEFAULT '{}'::jsonb,
            replacements_used smallint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_day_pools_user_id_local_date UNIQUE (user_id, local_date)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE quests.day_quests (
            id uuid PRIMARY KEY,
            pool_id uuid NOT NULL REFERENCES quests.day_pools (id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            local_date date NOT NULL,
            source text NOT NULL CHECK (source IN ('catalog', 'checkin_task', 'custom')),
            template_id integer REFERENCES quests.templates (id),
            title text NOT NULL,
            description text,
            category text NOT NULL CHECK (category IN {CATEGORY}),
            duration_min smallint NOT NULL CHECK (duration_min BETWEEN 1 AND 480),
            outdoor boolean NOT NULL DEFAULT false,
            why text,
            position smallint NOT NULL,
            state text NOT NULL
                CHECK (state IN ('offered', 'taken', 'replaced', 'completed', 'expired')),
            replaced_by_id uuid,
            reject_reason text CHECK (reject_reason IN ('no_time', 'dont_want', 'cant')),
            visibility text CHECK (visibility IN ('personal', 'routine', 'friends')),
            taken_at timestamptz,
            completed_at timestamptz,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_day_quests_catalog_template
                CHECK ((source = 'catalog') = (template_id IS NOT NULL))
        )
        """
    )
    op.execute("CREATE INDEX ix_day_pools_checkin_id ON quests.day_pools (checkin_id)")
    op.execute("CREATE INDEX ix_day_quests_pool_id ON quests.day_quests (pool_id)")
    op.execute(
        "CREATE INDEX ix_day_quests_user_id_local_date ON quests.day_quests (user_id, local_date)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE quests.day_quests")
    op.execute("DROP TABLE quests.day_pools")
    op.execute("DROP TABLE quests.checkins")
