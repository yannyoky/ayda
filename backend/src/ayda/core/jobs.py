"""A small background job queue in PostgreSQL (ADR 0006).

Jobs are claimed with `FOR UPDATE SKIP LOCKED`, so several workers can run side by side.
Payloads carry ids only; a failure stores the exception class name, never its message,
because messages can quote personal data.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import BigInteger, DateTime, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.selectable import TextualSelect

from ayda.core.models import core_metadata

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)
KEEP_FINISHED = timedelta(days=14)


class Base(DeclarativeBase):
    metadata = core_metadata("jobs")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: Mapping[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
) -> bool:
    """Add a job in the caller's transaction. With a dedupe key, a second job with the same
    key is ignored (False), which makes scheduling idempotent."""
    now = datetime.now(UTC)
    result = await session.execute(
        insert(Job)
        .values(
            kind=kind,
            payload=dict(payload or {}),
            dedupe_key=dedupe_key,
            run_at=run_at or now,
            max_attempts=max_attempts,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_jobs_dedupe_key")
        .returning(Job.id)
    )
    return result.scalar_one_or_none() is not None


Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class Periodic:
    """A function the worker calls every `every_s` seconds (e.g. the reminder scheduler)."""

    name: str
    every_s: float
    run: Callable[[AsyncSession, datetime], Awaitable[None]]


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** (attempts - 1), 3600))


def _claim(kind_filter: str) -> TextualSelect:
    return text(
        f"""
        UPDATE jobs.jobs SET status = 'running', locked_at = :now, attempts = attempts + 1
        WHERE id = (
            SELECT id FROM jobs.jobs
            WHERE status = 'queued' AND run_at <= :now {kind_filter}
            ORDER BY run_at, id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, kind, payload, attempts, max_attempts
        """
    ).columns(
        id=BigInteger, kind=Text, payload=JSONB, attempts=SmallInteger, max_attempts=SmallInteger
    )


_CLAIM = _claim("")
_CLAIM_ONLY = _claim("AND kind = ANY(CAST(:kinds AS text[]))")
_CLAIM_SKIP = _claim("AND kind <> ALL(CAST(:kinds AS text[]))")


class Worker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        handlers: Mapping[str, Handler],
        periodic: Sequence[Periodic] = (),
        poll_s: float = 1.0,
        only: Sequence[str] | None = None,
        skip: Sequence[str] | None = None,
    ) -> None:
        """`only` / `skip` make a lane: a worker that takes just those kinds, or all but
        them, so slow or urgent jobs (media) don't wait behind each other."""
        self._sessionmaker = sessionmaker
        self._handlers = dict(handlers)
        self._periodic = list(periodic)
        self._last_run: dict[str, float] = {}
        self._poll_s = poll_s
        self._claim = _CLAIM_ONLY if only is not None else _CLAIM_SKIP if skip else _CLAIM
        self._kinds = list(only if only is not None else skip or [])
        self._stopping = asyncio.Event()

    async def run_one(self, now: datetime | None = None) -> bool:
        """Claim and run one due job; False when there is none."""
        now = now or datetime.now(UTC)
        async with self._sessionmaker() as session:
            params: dict[str, Any] = {"now": now}
            if self._claim is not _CLAIM:
                params["kinds"] = self._kinds
            row = (await session.execute(self._claim, params)).first()
            await session.commit()
        if row is None:
            return False
        job_id, kind, payload, attempts, max_attempts = row
        handler = self._handlers.get(kind)
        error: str | None = None
        try:
            if handler is None:
                raise LookupError(f"no handler for {kind}")
            async with self._sessionmaker() as session:
                await handler(session, payload)
                await session.commit()
        except Exception as exc:
            error = type(exc).__name__
            log.warning("job %s (%s) failed: %s", job_id, kind, error)
        async with self._sessionmaker() as session:
            if error is None:
                params = {"id": job_id, "status": "done", "run_at": None, "error": None}
            elif attempts >= max_attempts:
                # Error level: reaches error tracking, so a job that gave up is noticed.
                log.error(
                    "job %s (%s) gave up after %d attempts: %s", job_id, kind, attempts, error
                )
                params = {"id": job_id, "status": "failed", "run_at": None, "error": error}
            else:
                params = {
                    "id": job_id,
                    "status": "queued",
                    "run_at": now + retry_delay(attempts),
                    "error": error,
                }
            await session.execute(
                text(
                    """
                    UPDATE jobs.jobs SET
                        status = :status,
                        run_at = COALESCE(CAST(:run_at AS timestamptz), run_at),
                        locked_at = NULL,
                        last_error = :error,
                        finished_at = CASE WHEN :status IN ('done', 'failed')
                                           THEN now() END
                    WHERE id = :id
                    """
                ),
                params,
            )
            await session.commit()
        return True

    async def run_due_periodic(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        for task in self._periodic:
            last = self._last_run.get(task.name)
            if last is not None and time.monotonic() - last < task.every_s:
                continue
            self._last_run[task.name] = time.monotonic()
            try:
                async with self._sessionmaker() as session:
                    await task.run(session, now)
                    await session.commit()
            except Exception as exc:
                log.warning("periodic %s failed: %s", task.name, type(exc).__name__)

    async def housekeeping(self, now: datetime | None = None) -> None:
        """Requeue jobs whose worker died and drop finished jobs after two weeks."""
        now = now or datetime.now(UTC)
        async with self._sessionmaker() as session:
            await session.execute(
                text(
                    "UPDATE jobs.jobs SET status = 'queued', locked_at = NULL"
                    " WHERE status = 'running' AND locked_at < :stale"
                ),
                {"stale": now - STALE_AFTER},
            )
            await session.execute(
                text("DELETE FROM jobs.jobs WHERE finished_at < :old"),
                {"old": now - KEEP_FINISHED},
            )
            await session.commit()

    def stop(self) -> None:
        self._stopping.set()

    async def run_forever(self) -> None:
        last_housekeeping = 0.0
        while not self._stopping.is_set():
            if time.monotonic() - last_housekeeping > 60:
                last_housekeeping = time.monotonic()
                await self.housekeeping()
            await self.run_due_periodic()
            while not self._stopping.is_set() and await self.run_one():
                pass
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._poll_s)


async def cancel_for_user(session: AsyncSession, user_id: str) -> None:
    """Drop queued jobs addressed to a user (account erasure)."""
    await session.execute(
        text("DELETE FROM jobs.jobs WHERE status = 'queued' AND payload->>'user_id' = :uid"),
        {"uid": user_id},
    )
