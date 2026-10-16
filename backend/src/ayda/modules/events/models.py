from sqlalchemy import Integer, Text
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
