"""Background worker: `python -m ayda.worker`. Same codebase and settings as the API."""

import asyncio
import signal
import uuid
from datetime import datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.app import notifications, privacy, reminders
from ayda.bot.sender import AiogramSender
from ayda.core import backup
from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.errors import init_error_tracking
from ayda.core.jobs import Handler, Periodic, Worker
from ayda.core.logging import configure_logging
from ayda.core.storage import Storage
from ayda.modules import social


def default_sender(settings: Settings) -> notifications.Sender:
    if settings.telegram_bot_token is None:
        return notifications.LogSender()
    return AiogramSender(Bot(settings.telegram_bot_token.get_secret_value()))


def build_worker(
    settings: Settings,
    db: Database,
    storage: Storage | None = None,
    sender: notifications.Sender | None = None,
) -> Worker:
    storage = storage or Storage(settings)
    sender = sender or default_sender(settings)
    reminders.register(settings)

    async def send_notification(session: AsyncSession, payload: dict[str, Any]) -> None:
        await notifications.send(session, sender, payload)

    async def process_media(session: AsyncSession, payload: dict[str, Any]) -> None:
        await social.process(session, storage, uuid.UUID(payload["media_id"]))

    async def delete_unattached_media(session: AsyncSession, now: datetime) -> None:
        await social.delete_unattached(session, storage, now)

    async def delete_files(session: AsyncSession, payload: dict[str, Any]) -> None:
        await storage.delete([str(k) for k in payload["keys"]])

    async def erase_account(session: AsyncSession, payload: dict[str, Any]) -> None:
        await privacy.erase_account(session, uuid.UUID(payload["account"]))

    async def purge_checkin_texts(session: AsyncSession, now: datetime) -> None:
        await privacy.purge_old_checkin_texts(session, now)

    async def run_backup(session: AsyncSession, payload: dict[str, Any]) -> None:
        await backup.create_backup(settings)

    handlers: dict[str, Handler] = {
        backup.BACKUP_JOB: run_backup,
        privacy.ERASE_JOB: erase_account,
        social.PROCESS_JOB: process_media,
        social.DELETE_FILES_JOB: delete_files,
        notifications.SEND_JOB: send_notification,
    }

    async def schedule_reminders(session: AsyncSession, now: datetime) -> None:
        await reminders.schedule_reminders(session, now)

    async def schedule_digests(session: AsyncSession, now: datetime) -> None:
        await reminders.schedule_digests(session, now)

    async def schedule_weekly(session: AsyncSession, now: datetime) -> None:
        await reminders.schedule_weekly(session, now)

    async def schedule_backup(session: AsyncSession, now: datetime) -> None:
        await backup.schedule_backup(session, settings, now)

    periodic = [
        Periodic("db.backup", 600, schedule_backup),
        Periodic("media.delete_unattached", 3600, delete_unattached_media),
        Periodic("reminders", 60, schedule_reminders),
        Periodic("digests", 300, schedule_digests),
        Periodic("weekly", 60, schedule_weekly),
        Periodic("checkins.purge_texts", 3600, purge_checkin_texts),
    ]
    return Worker(db.sessionmaker, handlers, periodic)


async def main() -> None:
    settings = get_settings()
    init_error_tracking(settings, "worker")
    db = Database(settings.database_url, echo=settings.database_echo)
    worker = build_worker(settings, db)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run_forever()
    finally:
        await db.dispose()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
