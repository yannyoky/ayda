import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.models import MODULE_SCHEMAS
from ayda.main import create_app
from tests.helpers import TEST_BOT_TOKEN

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Tests run against a real PostgreSQL with PostGIS (CI: a service container;
# locally: `docker compose up -d postgres` from the repository root).
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://ayda:ayda@localhost:5432/ayda_test"
)

# Reference data loaded by migrations; kept between tests.
REFERENCE_TABLES = {"events.cities", "quests.templates"}


async def _reset_schemas(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        for schema in MODULE_SCHEMAS:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    await engine.dispose()


async def _truncate_tables(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT schemaname || '.' || tablename FROM pg_tables"
                " WHERE schemaname = ANY(:schemas)"
            ),
            {"schemas": list(MODULE_SCHEMAS)},
        )
        tables = [r[0] for r in rows if r[0] not in REFERENCE_TABLES]
        if tables:
            await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    await engine.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logging"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated_database() -> str:
    asyncio.run(_reset_schemas(TEST_DATABASE_URL))
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    return TEST_DATABASE_URL


@pytest.fixture
def settings(migrated_database: str) -> Iterator[Settings]:
    yield Settings(
        environment="test",
        database_url=migrated_database,
        telegram_bot_token=SecretStr(TEST_BOT_TOKEN),
    )
    asyncio.run(_truncate_tables(migrated_database))


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database(settings.database_url)
    yield db
    await db.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    await app.state.db.dispose()
