"""Co-ops made of parts: kind, place, time, parts, checklists and hand-offs (M5, ADR 0010)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "('sport', 'walk', 'city', 'rest', 'project', 'social', 'home', 'learning')"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE quests.coops
            ADD COLUMN kind text NOT NULL DEFAULT 'same'
                CONSTRAINT ck_coops_kind CHECK (kind IN ('same', 'parts')),
            ADD COLUMN place jsonb,
            ADD COLUMN starts_at timestamptz
        """
    )
    op.execute(
        f"""
        CREATE TABLE quests.coop_parts (
            id uuid PRIMARY KEY,
            coop_id uuid NOT NULL REFERENCES quests.coops (id) ON DELETE CASCADE,
            position smallint NOT NULL,
            title text NOT NULL,
            category text NOT NULL CHECK (category IN {CATEGORY}),
            duration_min smallint NOT NULL CHECK (duration_min BETWEEN 1 AND 480),
            place jsonb,
            starts_at timestamptz,
            assignee_id uuid NOT NULL,
            opens_after_part_id uuid REFERENCES quests.coop_parts (id) ON DELETE SET NULL,
            -- the assignee's day quest for the part; set once the part is open
            day_quest_id uuid UNIQUE REFERENCES quests.day_quests (id) ON DELETE SET NULL,
            state text NOT NULL CHECK (state IN ('locked', 'open', 'done')),
            completed_at timestamptz,
            CONSTRAINT uq_coop_parts_coop_id_position UNIQUE (coop_id, position)
        )
        """
    )
    op.execute("CREATE INDEX ix_coop_parts_assignee_id ON quests.coop_parts (assignee_id)")
    op.execute(
        """
        CREATE TABLE quests.coop_part_items (
            id uuid PRIMARY KEY,
            part_id uuid NOT NULL REFERENCES quests.coop_parts (id) ON DELETE CASCADE,
            position smallint NOT NULL,
            text varchar(120) NOT NULL,
            done boolean NOT NULL DEFAULT false,
            done_at timestamptz,
            CONSTRAINT uq_coop_part_items_part_id_position UNIQUE (part_id, position)
        )
        """
    )
    # A row exists only while the offer waits for an answer: a part has at most one.
    op.execute(
        """
        CREATE TABLE quests.coop_handoffs (
            part_id uuid PRIMARY KEY REFERENCES quests.coop_parts (id) ON DELETE CASCADE,
            from_user_id uuid NOT NULL,
            to_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_coop_handoffs_to_user_id ON quests.coop_handoffs (to_user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE quests.coop_handoffs")
    op.execute("DROP TABLE quests.coop_part_items")
    op.execute("DROP TABLE quests.coop_parts")
    op.execute("ALTER TABLE quests.coops DROP COLUMN starts_at, DROP COLUMN place")
    op.execute("ALTER TABLE quests.coops DROP COLUMN kind")
