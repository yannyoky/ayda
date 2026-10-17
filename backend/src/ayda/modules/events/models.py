from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.models import module_metadata


class Base(DeclarativeBase):
    metadata = module_metadata("events")


class City(Base):
    """Reference data from `data/cities.csv`; the PostGIS `location` column is queried in SQL."""

    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    region_code: Mapped[str] = mapped_column(Text)
    region_name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text)
    population: Mapped[int] = mapped_column(Integer)


class Listing(Base):
    """An event occurrence from a source (ADR 0008); `location` is PostGIS, queried in SQL."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    city_id: Mapped[int] = mapped_column(Integer)
    region_code: Mapped[str] = mapped_column(Text)
    is_free: Mapped[bool] = mapped_column(Boolean)
    price_min: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
