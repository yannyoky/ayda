"""Background worker: `python -m ayda.worker`. Same codebase and settings as the API."""

import asyncio
import logging
import signal

from ayda.core.config import Settings, get_settings
from ayda.core.db import Database
from ayda.core.jobs import Handler, Periodic, Worker


def build_worker(settings: Settings, db: Database) -> Worker:
    handlers: dict[str, Handler] = {}
    periodic: list[Periodic] = []
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
