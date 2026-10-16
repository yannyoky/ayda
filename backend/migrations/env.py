import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from ayda.core.config import get_settings
from ayda.core.models import MODULE_SCHEMAS

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

# Migrations are hand-written; no autogenerate metadata.
target_metadata = None


def _url() -> str:
    url = config.attributes.get("database_url")
    return url if isinstance(url, str) else get_settings().database_url


def _include_name(name: str | None, type_: str, _parent: object) -> bool:
    return type_ != "schema" or name in MODULE_SCHEMAS


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=_include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
