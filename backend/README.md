# backend

Ayda backend: a FastAPI modular monolith (ADR 0002, 0003). Domain modules live in `src/ayda/modules/` and never import each other; shared runtime code (settings, database, errors) is in `src/ayda/core/`, HTTP routers in `src/ayda/api/`. The API implements `contracts/openapi.yaml` under `/api/v1` (ADR 0004).

Settings come only from environment variables; `.env.example` in the repository root lists them.

## Run locally

```sh
docker compose up -d postgres      # from the repository root: PostgreSQL + PostGIS + pgvector
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn ayda.main:app --reload
uv run python -m ayda.worker       # background jobs (ADR 0006), in another terminal
uv run python -m ayda.bot          # Telegram bot, polling (needs TELEGRAM_BOT_TOKEN)
```

`docker compose up` starts the API, the worker, the bot, MinIO and Centrifugo too.

## Checks (same as CI)

Tests need PostgreSQL with PostGIS; realtime integration tests also need Centrifugo (`docker compose up -d centrifugo`) and are skipped without it, except in CI. They use `TEST_DATABASE_URL` (default `postgresql+asyncpg://ayda:ayda@localhost:5432/ayda_test`, created by the compose service). Each run drops and re-migrates the module schemas of that database.

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest
```

Live checks of the external services (weather, listings, maps, LLM, Telegram, S3) are not part of that run; they need the network and keys. `uv run python -m ayda.smoke` prints one line per service, `uv run pytest -m live` runs the same checks as tests (see docs/deploy.md).

## Migrations

Hand-written Alembic migrations in `migrations/versions/`, one PostgreSQL schema per module.

```sh
uv run alembic revision -m "short description"
```
