import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from ayda.core import backup
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import enqueue
from ayda.core.storage import Storage

needs_pg_tools = pytest.mark.skipif(
    shutil.which("pg_dump") is None or shutil.which("pg_restore") is None,
    reason="pg_dump/pg_restore not installed",
)


def test_libpq_keeps_the_password_off_the_command_line() -> None:
    conn = backup.Libpq.from_url("postgresql+asyncpg://ayda:s3cret@db:6432/ayda")
    assert conn.args == ["--host", "db", "--port", "6432", "--username", "ayda", "--dbname", "ayda"]
    assert "s3cret" not in " ".join(conn.args)
    assert conn.env()["PGPASSWORD"] == "s3cret"


def test_backup_key_is_utc_and_sortable() -> None:
    now = datetime(2026, 10, 17, 3, 30, 5, tzinfo=UTC)
    assert backup.backup_key(now) == "db/2026-10-17T033005Z.dump"


async def test_backup_is_scheduled_once_a_day_after_the_backup_time(
    settings: Settings, database: Database
) -> None:
    before = datetime(2026, 10, 17, 0, 20, tzinfo=UTC)  # 03:20 in Moscow
    after = datetime(2026, 10, 17, 0, 40, tzinfo=UTC)  # 03:40 in Moscow
    async with database.sessionmaker() as session:
        assert not await backup.schedule_backup(session, settings, before)
        assert await backup.schedule_backup(session, settings, after)
        assert not await backup.schedule_backup(session, settings, after + timedelta(hours=5))
        assert await backup.schedule_backup(session, settings, after + timedelta(days=1))
        await session.commit()


async def test_prune_deletes_only_old_dumps(s3_settings: Settings) -> None:
    storage = Storage(s3_settings, bucket=s3_settings.backup_bucket)
    await storage.put("db/a.dump", b"a", "application/octet-stream")
    await storage.put("other/keep.txt", b"k", "text/plain")
    now = datetime.now(UTC)

    assert await backup.prune(storage, now - timedelta(days=1)) == []
    assert await backup.prune(storage, now + timedelta(minutes=1)) == ["db/a.dump"]
    assert [k for k, _ in await storage.list_keys("")] == ["other/keep.txt"]


@pytest.fixture
async def restore_url(s3_settings: Settings) -> AsyncIterator[str]:
    """An empty database next to the test database, dropped afterwards."""
    name = f"ayda_restore_{uuid.uuid4().hex[:8]}"
    admin_url = make_url(s3_settings.database_url).set(database="postgres")
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    yield (
        make_url(s3_settings.database_url).set(database=name).render_as_string(hide_password=False)
    )
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@needs_pg_tools
async def test_backup_and_restore_round_trip(
    s3_settings: Settings, database: Database, restore_url: str
) -> None:
    async with database.sessionmaker() as session:
        await enqueue(session, "test.kind", {"n": 1}, dedupe_key="backup-check")
        await session.commit()
        templates = await session.scalar(text("SELECT count(*) FROM quests.templates"))

    key = await backup.create_backup(s3_settings)
    assert await backup.list_backups(s3_settings) == [key]

    await backup.restore_backup(s3_settings, key, restore_url)
    restored = create_async_engine(restore_url)
    async with restored.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM quests.templates")) == templates
        assert (
            await conn.scalar(text("SELECT kind FROM jobs.jobs WHERE dedupe_key = 'backup-check'"))
            == "test.kind"
        )
        assert await conn.scalar(text("SELECT count(*) FROM alembic_version")) == 1
    await restored.dispose()


@needs_pg_tools
async def test_backup_failure_raises_without_uploading(s3_settings: Settings) -> None:
    broken = s3_settings.model_copy(
        update={"database_url": "postgresql+asyncpg://ayda:wrong@localhost:5432/no_such_db"}
    )
    with pytest.raises(backup.BackupError):
        await backup.create_backup(broken)
    assert await backup.list_backups(s3_settings) == []
