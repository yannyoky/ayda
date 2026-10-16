"""quests.coops, quests.coop_participants, co-op bonus rows in the points ledger (M2, US-18)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "('sport', 'walk', 'city', 'rest', 'project', 'social', 'home', 'learning')"


def upgrade() -> None:
    op.execute("ALTER TABLE quests.day_quests DROP CONSTRAINT day_quests_source_check")
    op.execute(
        "ALTER TABLE quests.day_quests ADD CONSTRAINT day_quests_source_check"
        " CHECK (source IN ('catalog', 'checkin_task', 'custom', 'coop'))"
    )
    op.execute(
        f"""
        CREATE TABLE quests.coops (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL,
            title text NOT NULL,
            description text,
            category text NOT NULL CHECK (category IN {CATEGORY}),
            duration_min smallint NOT NULL CHECK (duration_min BETWEEN 1 AND 480),
            outdoor boolean NOT NULL DEFAULT false,
            -- invitations can be accepted until the end of the owner's day
            expires_at timestamptz NOT NULL,
            bonus_awarded_at timestamptz,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_coops_owner_id ON quests.coops (owner_id)")
    op.execute(
        """
        CREATE TABLE quests.coop_participants (
            coop_id uuid NOT NULL REFERENCES quests.coops (id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            status text NOT NULL CHECK (status IN ('owner', 'invited', 'accepted', 'declined')),
            -- one co-op per day quest; set once the user owns or joins it
            day_quest_id uuid UNIQUE REFERENCES quests.day_quests (id) ON DELETE SET NULL,
            invited_at timestamptz NOT NULL,
            answered_at timestamptz,
            PRIMARY KEY (coop_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_coop_participants_user_id ON quests.coop_participants (user_id)")
    # A quest now has its own row and, in a co-op, one bonus row.
    op.execute(
        "ALTER TABLE quests.points_ledger ADD COLUMN kind text NOT NULL DEFAULT 'quest'"
        " CHECK (kind IN ('quest', 'coop_bonus'))"
    )
    op.execute("ALTER TABLE quests.points_ledger DROP CONSTRAINT uq_points_ledger_day_quest_id")
    op.execute(
        "ALTER TABLE quests.points_ledger ADD CONSTRAINT uq_points_ledger_day_quest_id_kind"
        " UNIQUE (day_quest_id, kind)"
    )


def downgrade() -> None:
    op.execute("SET LOCAL ayda.points_maintenance = 'on'")
    op.execute("DELETE FROM quests.points_ledger WHERE kind = 'coop_bonus'")
    op.execute(
        "ALTER TABLE quests.points_ledger DROP CONSTRAINT uq_points_ledger_day_quest_id_kind"
    )
    op.execute(
        "ALTER TABLE quests.points_ledger ADD CONSTRAINT uq_points_ledger_day_quest_id"
        " UNIQUE (day_quest_id)"
    )
    op.execute("ALTER TABLE quests.points_ledger DROP COLUMN kind")
    op.execute("DROP TABLE quests.coop_participants")
    op.execute("DROP TABLE quests.coops")
    op.execute(
        "DELETE FROM quests.points_ledger WHERE day_quest_id IN"
        " (SELECT id FROM quests.day_quests WHERE source = 'coop')"
    )
    op.execute("DELETE FROM quests.day_quests WHERE source = 'coop'")
    op.execute("ALTER TABLE quests.day_quests DROP CONSTRAINT day_quests_source_check")
    op.execute(
        "ALTER TABLE quests.day_quests ADD CONSTRAINT day_quests_source_check"
        " CHECK (source IN ('catalog', 'checkin_task', 'custom'))"
    )
