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
```

`docker compose up` starts the API and Centrifugo too.

## Checks (same as CI)

Tests need PostgreSQL with PostGIS; they use `TEST_DATABASE_URL` (default `postgresql+asyncpg://ayda:ayda@localhost:5432/ayda_test`, created by the compose service). Each run drops and re-migrates the module schemas of that database.

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest
```

## Migrations

Hand-written Alembic migrations in `migrations/versions/`, one PostgreSQL schema per module.

```sh
uv run alembic revision -m "short description"
```
