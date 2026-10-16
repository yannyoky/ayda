from sqlalchemy import MetaData

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Each module owns the PostgreSQL schema of the same name (docs/architecture.md).
MODULE_SCHEMAS = (
    "auth",
    "habits",
    "quests",
    "assistant",
    "social",
    "chat",
    "events",
    "analytics",
)

# Shared infrastructure owned by `ayda.core` rather than a module.
CORE_SCHEMAS = ("jobs",)
ALL_SCHEMAS = MODULE_SCHEMAS + CORE_SCHEMAS


def module_metadata(schema: str) -> MetaData:
    assert schema in MODULE_SCHEMAS, schema
    return MetaData(schema=schema, naming_convention=NAMING_CONVENTION)


def core_metadata(schema: str) -> MetaData:
    assert schema in CORE_SCHEMAS, schema
    return MetaData(schema=schema, naming_convention=NAMING_CONVENTION)
