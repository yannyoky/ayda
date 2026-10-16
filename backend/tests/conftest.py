import asyncio
import os
import socket
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import boto3
import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from moto.server import ThreadedMotoServer
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.models import ALL_SCHEMAS
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
        for schema in ALL_SCHEMAS:
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
            {"schemas": list(ALL_SCHEMAS)},
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
        # Presigning needs credentials, not a reachable server.
        s3_access_key_id=SecretStr("test"),
        s3_secret_access_key=SecretStr("test"),
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


# S3 in tests: a local moto server, one fresh bucket per test.
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def s3_url() -> Iterator[str]:
    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    yield f"http://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def s3_settings(settings: Settings, s3_url: str) -> Settings:
    updated = settings.model_copy(
        update={
            "s3_endpoint_url": s3_url,
            "s3_bucket": f"test-{uuid.uuid4().hex[:8]}",
            "backup_bucket": f"backup-{uuid.uuid4().hex[:8]}",
            "s3_access_key_id": SecretStr("test"),
            "s3_secret_access_key": SecretStr("test"),
            "s3_region": "us-east-1",
        }
    )
    s3 = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=s3_url,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.create_bucket(Bucket=updated.s3_bucket)
    s3.create_bucket(Bucket=updated.backup_bucket)
    return updated
