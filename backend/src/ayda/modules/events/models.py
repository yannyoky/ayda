import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
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


class Venue(Base):
    """A place from OpenStreetMap (ADR 0011); `location` is PostGIS, queried in SQL."""

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    osm_type: Mapped[str] = mapped_column(Text)
    osm_id: Mapped[int] = mapped_column(BigInteger)
    city_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    cuisine: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    opening_hours: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VenueLoad(Base):
    __tablename__ = "venue_loads"

    city_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    venues: Mapped[int] = mapped_column(Integer)


class VenueReport(Base):
    """A user's "Не работает" on a venue; the user id is kept only to count people once."""

    __tablename__ = "venue_reports"

    venue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
