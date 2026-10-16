from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.core.db import Database
from ayda.core.jobs import Job, Periodic, Worker, enqueue, retry_delay

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


async def jobs(database: Database) -> list[Job]:
    async with database.sessionmaker() as session:
        return list(await session.scalars(select(Job).order_by(Job.id)))


async def test_job_runs_once_and_dedupe_key_is_idempotent(database: Database) -> None:
    seen: list[dict[str, Any]] = []

    async def handler(session: AsyncSession, payload: dict[str, Any]) -> None:
        seen.append(payload)

    async with database.sessionmaker() as session:
        assert await enqueue(session, "hello", {"user_id": "u1"}, dedupe_key="hello:u1")
        assert not await enqueue(session, "hello", {"user_id": "u1"}, dedupe_key="hello:u1")
        await session.commit()

    worker = Worker(database.sessionmaker, {"hello": handler})
    assert await worker.run_one(datetime.now(UTC))
    assert not await worker.run_one(datetime.now(UTC))

    assert seen == [{"user_id": "u1"}]
    [job] = await jobs(database)
    assert job.status == "done" and job.attempts == 1 and job.finished_at is not None


async def test_future_jobs_wait(database: Database) -> None:
    async with database.sessionmaker() as session:
        await enqueue(session, "later", run_at=NOW + timedelta(minutes=5))
        await session.commit()

    async def handler(session: AsyncSession, payload: dict[str, Any]) -> None:
        return None

    worker = Worker(database.sessionmaker, {"later": handler})
    assert not await worker.run_one(NOW)
    assert await worker.run_one(NOW + timedelta(minutes=5))


async def test_failure_retries_with_backoff_then_fails(database: Database) -> None:
    async def handler(session: AsyncSession, payload: dict[str, Any]) -> None:
        raise ValueError("secret text from a user")

    async with database.sessionmaker() as session:
        await enqueue(session, "boom", run_at=NOW, max_attempts=2)
        await session.commit()
    worker = Worker(database.sessionmaker, {"boom": handler})

    assert await worker.run_one(NOW)
    [job] = await jobs(database)
    assert job.status == "queued" and job.run_at == NOW + retry_delay(1)
    assert job.last_error == "ValueError"  # never the message

    assert not await worker.run_one(NOW + timedelta(seconds=10))
    assert await worker.run_one(NOW + timedelta(minutes=1))
    [job] = await jobs(database)
    assert job.status == "failed" and job.attempts == 2


async def test_unknown_kind_fails_without_crashing(database: Database) -> None:
    async with database.sessionmaker() as session:
        await enqueue(session, "nobody", max_attempts=1)
        await session.commit()

    assert await Worker(database.sessionmaker, {}).run_one()
    [job] = await jobs(database)
    assert job.status == "failed" and job.last_error == "LookupError"


async def test_stale_running_jobs_are_requeued(database: Database) -> None:
    async with database.sessionmaker() as session:
        await enqueue(session, "stuck", run_at=NOW)
        await session.commit()
    async with database.sessionmaker() as session:
        job = (await session.scalars(select(Job))).one()
        job.status, job.locked_at = "running", NOW - timedelta(minutes=30)
        await session.commit()

    await Worker(database.sessionmaker, {}).housekeeping(NOW)

    [job] = await jobs(database)
    assert job.status == "queued" and job.locked_at is None


async def test_periodic_runs_at_its_interval(database: Database) -> None:
    calls: list[datetime] = []

    async def tick(session: AsyncSession, now: datetime) -> None:
        calls.append(now)

    worker = Worker(database.sessionmaker, {}, [Periodic("tick", 3600, tick)])
    await worker.run_due_periodic(NOW)
    await worker.run_due_periodic(NOW)

    assert calls == [NOW]


def test_retry_delay_grows_and_caps() -> None:
    assert [retry_delay(n).total_seconds() for n in (1, 2, 3, 10)] == [30, 60, 120, 3600]
