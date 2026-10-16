"""Background worker: `python -m ayda.worker`. Same codebase and settings as the API."""

import asyncio
import logging
import signal
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.jobs import Handler, Periodic, Worker
from ayda.core.storage import Storage
from ayda.modules import social


def build_worker(settings: Settings, db: Database, storage: Storage | None = None) -> Worker:
    storage = storage or Storage(settings)

    async def process_media(session: AsyncSession, payload: dict[str, Any]) -> None:
        await social.process(session, storage, uuid.UUID(payload["media_id"]))

    async def delete_unattached_media(session: AsyncSession, now: datetime) -> None:
        await social.delete_unattached(session, storage, now)

    handlers: dict[str, Handler] = {social.PROCESS_JOB: process_media}
    periodic = [Periodic("media.delete_unattached", 3600, delete_unattached_media)]
    return Worker(db.sessionmaker, handlers, periodic)


async def main() -> None:
    settings = get_settings()
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
