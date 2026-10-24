"""Quest catalog: the only source of suggested quests (the LLM picks from it, never invents)."""

import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.quests.models import Template

CATALOG_PATH = Path(__file__).parent / "data" / "catalog.yaml"

Category = Literal["sport", "walk", "city", "rest", "project", "social", "home", "learning"]
CATEGORIES: tuple[Category, ...] = (
    "sport",
    "walk",
    "city",
    "rest",
    "project",
    "social",
    "home",
    "learning",
)


class WeatherRule(BaseModel, extra="forbid"):
    no_rain: bool = False
    no_wind: bool = False
    min_temp_c: float | None = None
    max_temp_c: float | None = None


class CatalogQuest(BaseModel, extra="forbid"):
    id: int = Field(gt=0)
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=300)
    category: Category
    duration_min: int = Field(ge=5, le=480)
    outdoor: bool
    weather: WeatherRule = WeatherRule()
    tags: list[str] = []
    interests: list[str] = []
    active: bool = True


class Catalog(BaseModel, extra="forbid"):
    version: int
    quests: list[CatalogQuest]

    @model_validator(mode="after")
    def _unique(self) -> "Catalog":
        ids = [q.id for q in self.quests]
        slugs = [q.slug for q in self.quests]
        if len(set(ids)) != len(ids) or len(set(slugs)) != len(slugs):
            raise ValueError("quest ids and slugs must be unique")
        return self


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    with path.open(encoding="utf-8") as f:
        return Catalog.model_validate(yaml.safe_load(f))


def template_values(q: CatalogQuest) -> dict[str, object]:
    return {
        "slug": q.slug,
        "title": q.title,
        "description": q.description,
        "category": q.category,
        "duration_min": q.duration_min,
        "outdoor": q.outdoor,
        "weather": q.weather.model_dump(exclude_defaults=True),
        "tags": q.tags,
        "interest_codes": q.interests,
        "active": q.active,
    }


async def sync_catalog(session: AsyncSession, catalog: Catalog | None = None) -> int:
    """Upsert every quest by id; quests missing from the file are deactivated, never deleted."""
    catalog = catalog or load_catalog()
    for q in catalog.quests:
        values = template_values(q)
        await session.execute(
            insert(Template)
            .values(id=q.id, **values)
            .on_conflict_do_update(index_elements=[Template.id], set_=values)
        )
    ids = [q.id for q in catalog.quests]
    await session.execute(update(Template).where(Template.id.not_in(ids)).values(active=False))
    return len(ids)


async def _main() -> None:
    from ayda.core.config import get_settings
    from ayda.core.db import Database

    db = Database(get_settings().database_url)
    async with db.sessionmaker() as session:
        count = await sync_catalog(session)
        await session.commit()
    await db.dispose()
    print(f"synced {count} quests", file=sys.stderr)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
