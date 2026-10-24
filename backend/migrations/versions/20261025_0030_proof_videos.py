"""social.media: a video or a circle as quest proof, deleted after 30 days (ADR 0019)

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE social.media ADD COLUMN kind text NOT NULL DEFAULT 'photo' "
        "CHECK (kind IN ('photo', 'video', 'video_note'))"
    )
    op.execute("ALTER TABLE social.media ADD COLUMN duration_ms integer")
    for name in ("content_type", "size_bytes", "status"):
        op.execute(f"ALTER TABLE social.media DROP CONSTRAINT media_{name}_check")
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT media_content_type_check CHECK (content_type IN "
        "('image/jpeg', 'image/png', 'image/heic', 'image/webp', "
        "'video/webm', 'video/mp4', 'video/quicktime'))"
    )
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT media_size_bytes_check "
        "CHECK (size_bytes BETWEEN 1 AND 52428800)"
    )
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT media_status_check "
        "CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'expired'))"
    )
    op.execute(
        "CREATE INDEX ix_media_videos ON social.media (created_at) "
        "WHERE kind <> 'photo' AND status <> 'expired'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX social.ix_media_videos")
    op.execute("DELETE FROM social.media WHERE kind <> 'photo'")
    for name in ("content_type", "size_bytes", "status"):
        op.execute(f"ALTER TABLE social.media DROP CONSTRAINT media_{name}_check")
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT media_content_type_check CHECK (content_type IN "
        "('image/jpeg', 'image/png', 'image/heic', 'image/webp'))"
    )
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT media_size_bytes_check "
        "CHECK (size_bytes BETWEEN 1 AND 10485760)"
    )
    op.execute(
        "ALTER TABLE social.media ADD CONSTRAINT media_status_check "
        "CHECK (status IN ('pending', 'processing', 'ready', 'failed'))"
    )
    op.execute("ALTER TABLE social.media DROP COLUMN duration_ms")
    op.execute("ALTER TABLE social.media DROP COLUMN kind")
