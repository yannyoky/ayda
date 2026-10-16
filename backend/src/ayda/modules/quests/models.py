from sqlalchemy import Boolean, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.models import module_metadata


class Base(DeclarativeBase):
    metadata = module_metadata("quests")


class Template(Base):
    """A catalog quest, synced from `data/catalog.yaml`."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    outdoor: Mapped[bool] = mapped_column(Boolean)
    weather: Mapped[dict[str, object]] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text))
    goal_codes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    active: Mapped[bool] = mapped_column(Boolean)
