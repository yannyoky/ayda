# 0006. Own job queue on PostgreSQL

English · [Русский](../ru/decisions/0006-job-queue.md)

## Context
ADR 0002 chose a job queue in PostgreSQL (no Redis). M1 needs it for photo processing (EXIF removal), morning and evening reminders, the hourly likes digest and the Sunday summary, and later for account erasure and check-in text retention. Load is tiny (about 5 users). The ready-made option, procrastinate, needs the psycopg driver next to our asyncpg, keeps its own schema migrations outside Alembic, and brings more features than these jobs use.

## Decision
A small queue in `ayda.core.jobs`: one table `jobs.jobs` (kind, payload, dedupe key, status, run_at, attempts), jobs claimed with `UPDATE ... FOR UPDATE SKIP LOCKED`, retries with exponential backoff up to `max_attempts`, stale running jobs requeued after 10 minutes, finished jobs deleted after 14 days. Periodic tasks (the reminder scheduler, digests) are functions the worker calls on an interval; they enqueue jobs with a dedupe key such as `reminder:morning:<user>:<date>`, so a restart or a second worker never sends twice. The worker is `python -m ayda.worker`, the same package and settings as the API. Payloads hold ids only, and a failure stores the exception class name, never its message.

## Consequences
No new driver or service, migrations stay in Alembic, and the queue is about 200 lines we fully control and test. Features such as job priorities, cron syntax or a dashboard are not available; if they become necessary, procrastinate can replace this module behind the same `enqueue` call.
