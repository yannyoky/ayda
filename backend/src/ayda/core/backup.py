"""Daily PostgreSQL backups to the private backup bucket, and the restore used to check them.

`pg_dump --format=custom` of the whole database, uploaded as `db/<UTC time>.dump`, or
`.dump.age` when `BACKUP_AGE_RECIPIENT` is set: then the dump is encrypted with that age
public key and only the holder of the private key, kept off the server, can read it. Dumps
older than `BACKUP_KEEP_DAYS` are deleted after each successful upload (0 keeps all). The
password goes to pg_dump through PGPASSWORD, never on the command line.

CLI (run inside the backend image on the VPS):
    python -m ayda.core.backup create
    python -m ayda.core.backup list
    python -m ayda.core.backup restore <key> --target-url <database url> [--identity <file>]
Restore into an empty database and check it before switching anything to it. An encrypted
dump needs `--identity`: the age private key file, copied in for the restore and removed after.
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


def backup_storage(settings: Settings) -> Storage:
    """The backup bucket, with its own keys when they are set."""
    keys = None
    if settings.backup_s3_access_key_id and settings.backup_s3_secret_access_key:
        keys = (settings.backup_s3_access_key_id, settings.backup_s3_secret_access_key)
    return Storage(settings, bucket=settings.backup_bucket, keys=keys)


ENCRYPTED_SUFFIX = ".age"


def backup_key(now: datetime, encrypted: bool = False) -> str:
    suffix = ENCRYPTED_SUFFIX if encrypted else ""
    return f"{PREFIX}{now.astimezone(UTC):%Y-%m-%dT%H%M%SZ}.dump{suffix}"


async def create_backup(
    settings: Settings, now: datetime | None = None, storage: Storage | None = None
) -> str:
    """Dump the database, upload it and prune old dumps; returns the new key."""
    now = now or datetime.now(UTC)
    storage = storage or backup_storage(settings)
    conn = Libpq.from_url(settings.database_url)
    recipient = settings.backup_age_recipient
    key = backup_key(now, encrypted=recipient is not None)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "ayda.dump")
        await _run(
            "pg_dump", "--format=custom", "--no-owner", "--file", path, *conn.args, env=conn.env()
        )
        if recipient is not None:
            plain, path = path, path + ENCRYPTED_SUFFIX
            await _run("age", "--encrypt", "--recipient", recipient, "--output", path, plain,
                       env=dict(os.environ))  # fmt: skip
            Path(plain).unlink()
        else:
            log.warning("BACKUP_AGE_RECIPIENT is not set: the backup is not encrypted")
        await storage.upload_file(path, key)
    if settings.backup_keep_days > 0:
        await prune(storage, now - timedelta(days=settings.backup_keep_days))
    log.info("backup uploaded: %s", key)
    return key


async def prune(storage: Storage, older_than: datetime) -> list[str]:
    old = [k for k, modified in await storage.list_keys(PREFIX) if modified < older_than]
    await storage.delete(old)
    return old


async def list_backups(settings: Settings, storage: Storage | None = None) -> list[str]:
    storage = storage or backup_storage(settings)
    return sorted(k for k, _ in await storage.list_keys(PREFIX))


async def restore_backup(
    settings: Settings,
    key: str,
    target_url: str,
    storage: Storage | None = None,
    identity: str | None = None,
) -> None:
    """Restore a dump into `target_url` (an existing, preferably empty, database).
    An encrypted dump (`.age`) needs `identity`, the path of the age private key file."""
    storage = storage or backup_storage(settings)
    conn = Libpq.from_url(target_url)
    encrypted = key.endswith(ENCRYPTED_SUFFIX)
    if encrypted and identity is None:
        raise BackupError("the dump is encrypted: pass the age private key file (--identity)")
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "ayda.dump")
        if encrypted:
            assert identity is not None
            await storage.download_file(key, path + ENCRYPTED_SUFFIX)
            await _run("age", "--decrypt", "--identity", identity, "--output", path,
                       path + ENCRYPTED_SUFFIX, env=dict(os.environ))  # fmt: skip
        else:
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
    restore.add_argument("--identity", help="age private key file, for an encrypted dump")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "create":
        print(await create_backup(settings))
    elif args.command == "list":
        for key in await list_backups(settings):
            print(key)
    else:
        await restore_backup(settings, args.key, args.target_url, identity=args.identity)
        print(f"restored {args.key}")


if __name__ == "__main__":
    asyncio.run(_cli())
