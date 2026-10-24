"""Background worker: `python -m ayda.worker`. Same codebase and settings as the API."""

import asyncio
import signal
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.app import chat, coop, notifications, privacy, realtime, reminders
from ayda.app import events as local_events
from ayda.bot.sender import AiogramSender
from ayda.core import backup
from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.errors import init_error_tracking
from ayda.core.jobs import Handler, Periodic, Worker
from ayda.core.logging import configure_logging
from ayda.core.push import FcmSender, LogPushSender
from ayda.core.realtime import Realtime
from ayda.core.storage import Storage
from ayda.modules import social
from ayda.modules.events import EventSource, OverpassSource


def default_sender(settings: Settings) -> notifications.Sender:
    if settings.telegram_bot_token is None:
        return notifications.LogSender()
    return AiogramSender(Bot(settings.telegram_bot_token.get_secret_value()))


def default_push_sender(settings: Settings) -> notifications.PushSender:
    if settings.fcm_service_account_json is None:
        return LogPushSender()
    return FcmSender(settings.fcm_service_account_json.get_secret_value())


def build_worker(
    settings: Settings,
    db: Database,
    storage: Storage | None = None,
    sender: notifications.Sender | None = None,
    push_sender: notifications.PushSender | None = None,
    realtime_client: Realtime | None = None,
    event_sources: Sequence[EventSource] | None = None,
    venues: OverpassSource | None = None,
) -> Worker:
    storage = storage or Storage(settings)
    publisher = realtime_client or Realtime(settings)
    sender = sender or default_sender(settings)
    push_sender = push_sender or default_push_sender(settings)
    if event_sources is None:
        event_sources = local_events.default_sources(settings, local_events.source_http())
    if venues is None:
        venues = local_events.venue_source(settings, local_events.venue_http())
    reminders.register(settings)
    chat.register(settings)
    chat.use_storage(storage)
    coop.register(settings)

    async def send_notification(session: AsyncSession, payload: dict[str, Any]) -> None:
        await notifications.send(session, sender, payload, push_sender)

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

    async def purge_assistant_chats(session: AsyncSession, now: datetime) -> None:
        await privacy.purge_old_assistant_chats(session, now)

    async def process_attachment(session: AsyncSession, payload: dict[str, Any]) -> None:
        await chat.process_attachment(
            session, storage, publisher, uuid.UUID(payload["attachment_id"])
        )

    async def delete_unsent_attachments(session: AsyncSession, now: datetime) -> None:
        await chat.delete_unsent_uploads(session, now)

    async def purge_coop_chats(session: AsyncSession, now: datetime) -> None:
        await chat.purge_ended_coop_chats(session, now)

    async def run_backup(session: AsyncSession, payload: dict[str, Any]) -> None:
        await backup.create_backup(settings)

    async def publish_event(session: AsyncSession, payload: dict[str, Any]) -> None:
        await realtime.deliver(session, publisher, payload["kind"], payload["params"])

    async def ingest_events(session: AsyncSession, payload: dict[str, Any]) -> None:
        await local_events.run_ingest(session, event_sources, datetime.now(UTC))

    async def load_venues(session: AsyncSession, payload: dict[str, Any]) -> None:
        if venues is not None:
            await local_events.run_venues(
                session, venues, settings.venues_radius_m, datetime.now(UTC)
            )

    handlers: dict[str, Handler] = {
        local_events.INGEST_JOB: ingest_events,
        local_events.VENUES_JOB: load_venues,
        realtime.PUBLISH_JOB: publish_event,
        backup.BACKUP_JOB: run_backup,
        privacy.ERASE_JOB: erase_account,
        social.PROCESS_JOB: process_media,
        chat.ATTACHMENT_JOB: process_attachment,
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

    async def schedule_events(session: AsyncSession, now: datetime) -> None:
        await local_events.schedule_ingest(session, settings, now)

    async def schedule_venues(session: AsyncSession, now: datetime) -> None:
        await local_events.schedule_venues(session, settings, now)

    periodic = [
        Periodic("events.ingest", 600, schedule_events),
        Periodic("events.venues", 600, schedule_venues),
        Periodic("db.backup", 600, schedule_backup),
        Periodic("media.delete_unattached", 3600, delete_unattached_media),
        Periodic("reminders", 60, schedule_reminders),
        Periodic("digests", 300, schedule_digests),
        Periodic("weekly", 60, schedule_weekly),
        Periodic("checkins.purge_texts", 3600, purge_checkin_texts),
        Periodic("assistant.purge_chats", 3600, purge_assistant_chats),
        Periodic("chat.purge_coops", 3600, purge_coop_chats),
        Periodic("chat.delete_unsent", 3600, delete_unsent_attachments),
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
