"""quests.templates: the quest catalog, seeded from catalog.yaml

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16

Later catalog edits are applied with `python -m ayda.modules.quests.catalog`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from ayda.modules.quests.catalog import load_catalog, template_values

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quests.templates (
            id integer PRIMARY KEY,
            slug text NOT NULL CONSTRAINT uq_templates_slug UNIQUE,
            title text NOT NULL,
            description text NOT NULL,
            category text NOT NULL CONSTRAINT ck_templates_category CHECK (category IN
                ('sport', 'walk', 'city', 'rest', 'project', 'social', 'home', 'learning')),
            duration_min smallint NOT NULL,
            outdoor boolean NOT NULL,
            weather jsonb NOT NULL DEFAULT '{}'::jsonb,
            tags text[] NOT NULL DEFAULT '{}',
            goal_codes text[] NOT NULL DEFAULT '{}',
            active boolean NOT NULL DEFAULT true
        )
        """
    )
    table = sa.table(
        "templates",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.Text),
        sa.column("title", sa.Text),
        sa.column("description", sa.Text),
        sa.column("category", sa.Text),
        sa.column("duration_min", sa.SmallInteger),
        sa.column("outdoor", sa.Boolean),
        sa.column("weather", sa.JSON),
        sa.column("tags", sa.ARRAY(sa.Text)),
        sa.column("goal_codes", sa.ARRAY(sa.Text)),
        sa.column("active", sa.Boolean),
        schema="quests",
    )
    op.bulk_insert(table, [{"id": q.id, **template_values(q)} for q in load_catalog().quests])


def downgrade() -> None:
    op.execute("DROP TABLE quests.templates")
