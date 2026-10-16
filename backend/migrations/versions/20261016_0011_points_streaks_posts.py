"""quests.points_ledger, quests.streaks, social.posts

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "('sport', 'walk', 'city', 'rest', 'project', 'social', 'home', 'learning')"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quests.points_ledger (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL,
            day_quest_id uuid NOT NULL REFERENCES quests.day_quests (id),
            local_date date NOT NULL,
            week_start date NOT NULL,
            points integer NOT NULL CHECK (points >= 0),
            breakdown jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_points_ledger_day_quest_id UNIQUE (day_quest_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_points_ledger_week_start_user_id"
        " ON quests.points_ledger (week_start, user_id)"
    )
    op.execute(
        "CREATE INDEX ix_points_ledger_user_id_local_date"
        " ON quests.points_ledger (user_id, local_date)"
    )
    # Append-only like analytics.events: account erasure is the only maintenance path.
    op.execute(
        """
        CREATE FUNCTION quests.points_ledger_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('ayda.points_maintenance', true) = 'on' THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION 'quests.points_ledger is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER points_ledger_append_only
        BEFORE UPDATE OR DELETE ON quests.points_ledger
        FOR EACH ROW EXECUTE FUNCTION quests.points_ledger_append_only()
        """
    )
    op.execute(
        """
        CREATE TABLE quests.streaks (
            user_id uuid PRIMARY KEY,
            current_days integer NOT NULL DEFAULT 0,
            best_days integer NOT NULL DEFAULT 0,
            last_counted_date date,
            freeze_week_start date,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE social.posts (
            id uuid PRIMARY KEY,
            author_id uuid NOT NULL,
            day_quest_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('proof', 'routine')),
            quest_title text,
            category text NOT NULL CHECK (category IN {CATEGORY}),
            caption varchar(500),
            local_date date NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            CONSTRAINT uq_posts_day_quest_id UNIQUE (day_quest_id),
            CONSTRAINT ck_posts_routine_is_bare
                CHECK (kind = 'proof' OR (quest_title IS NULL AND caption IS NULL))
        )
        """
    )
    op.execute("CREATE INDEX ix_posts_author_id_created_at ON social.posts (author_id, created_at)")
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT fk_media_post_id_posts"
        " FOREIGN KEY (post_id) REFERENCES social.posts (id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE social.media DROP CONSTRAINT fk_media_post_id_posts")
    op.execute("DROP TABLE social.posts")
    op.execute("DROP TABLE quests.streaks")
    op.execute("DROP TABLE quests.points_ledger")
    op.execute("DROP FUNCTION quests.points_ledger_append_only()")
