"""Daily PostgreSQL backups to the private backup bucket, and the restore used to check them.

`pg_dump --format=custom` of the whole database, uploaded as `db/<UTC time>.dump`; dumps
older than `BACKUP_KEEP_DAYS` are deleted after each successful upload. The password goes to
pg_dump through PGPASSWORD, never on the command line.

CLI (run inside the backend image on the VPS):
    python -m ayda.core.backup create
    python -m ayda.core.backup list
    python -m ayda.core.backup restore <key> --target-url <database url>
Restore into an empty database and check it before switching anything to it.
"""

import argparse
import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.config import Settings, get_settings
from ayda.core.jobs import enqueue
from ayda.core.storage import Storage

log = logging.getLogger(__name__)

PREFIX = "db/"
BACKUP_JOB = "db.backup"


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Libpq:
    """Connection arguments for pg_dump / pg_restore, with the password kept apart."""

    args: list[str]
    password: str | None

    @classmethod
    def from_url(cls, url: str) -> "Libpq":
        u = make_url(url)
        args = ["--host", u.host or "localhost", "--port", str(u.port or 5432)]
        if u.username:
            args += ["--username", u.username]
        args += ["--dbname", u.database or "postgres"]
        return cls(args, u.password)

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.password is not None:
            env["PGPASSWORD"] = self.password
        return env


async def _run(*cmd: str, env: dict[str, str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # pg tools' stderr names objects, not row data; keep only the last line.
        last = stderr.decode(errors="replace").strip().splitlines()[-1:] or [""]
        raise BackupError(f"{cmd[0]} exited with {proc.returncode}: {last[0][:200]}")


def backup_key(now: datetime) -> str:
    return f"{PREFIX}{now.astimezone(UTC):%Y-%m-%dT%H%M%SZ}.dump"


async def create_backup(
    settings: Settings, now: datetime | None = None, storage: Storage | None = None
) -> str:
    """Dump the database, upload it and prune old dumps; returns the new key."""
    now = now or datetime.now(UTC)
    storage = storage or Storage(settings, bucket=settings.backup_bucket)
    conn = Libpq.from_url(settings.database_url)
    key = backup_key(now)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "ayda.dump")
        await _run(
            "pg_dump", "--format=custom", "--no-owner", "--file", path, *conn.args, env=conn.env()
        )
        await storage.upload_file(path, key)
    await prune(storage, now - timedelta(days=settings.backup_keep_days))
    log.info("backup uploaded: %s", key)
    return key


async def prune(storage: Storage, older_than: datetime) -> list[str]:
    old = [k for k, modified in await storage.list_keys(PREFIX) if modified < older_than]
    await storage.delete(old)
    return old


async def list_backups(settings: Settings, storage: Storage | None = None) -> list[str]:
    storage = storage or Storage(settings, bucket=settings.backup_bucket)
    return sorted(k for k, _ in await storage.list_keys(PREFIX))


async def restore_backup(
    settings: Settings, key: str, target_url: str, storage: Storage | None = None
) -> None:
    """Restore a dump into `target_url` (an existing, preferably empty, database)."""
    storage = storage or Storage(settings, bucket=settings.backup_bucket)
    conn = Libpq.from_url(target_url)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "ayda.dump")
        await storage.download_file(key, path)
        await _run(
            "pg_restore",
            "--no-owner",
            "--clean",
            "--if-exists",
            "--exit-on-error",
            *conn.args,
            path,
            env=conn.env(),
        )


def _due_date(settings: Settings, now: datetime) -> str | None:
    """The local date whose backup is due now, or None before today's backup time."""
    local = now.astimezone(ZoneInfo(settings.backup_timezone))
    if local.time() < settings.backup_at:
        return None
    return local.date().isoformat()


async def schedule_backup(session: AsyncSession, settings: Settings, now: datetime) -> bool:
    """Queue today's backup once (dedupe key per local date); the job retries on failure."""
    day = _due_date(settings, now)
    if day is None:
        return False
    return await enqueue(session, BACKUP_JOB, {"day": day}, dedupe_key=f"{BACKUP_JOB}:{day}")


async def _cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ayda.core.backup")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create")
    sub.add_parser("list")
    restore = sub.add_parser("restore")
    restore.add_argument("key")
    restore.add_argument("--target-url", required=True)
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "create":
        print(await create_backup(settings))
    elif args.command == "list":
        for key in await list_backups(settings):
            print(key)
    else:
        await restore_backup(settings, args.key, args.target_url)
        print(f"restored {args.key}")


if __name__ == "__main__":
    asyncio.run(_cli())
