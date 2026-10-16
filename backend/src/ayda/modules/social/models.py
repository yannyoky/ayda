import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.ids import uuid7
from ayda.core.models import module_metadata


class Base(DeclarativeBase):
    metadata = module_metadata("social")


class Media(Base):
    """A photo. `storage_key` is the upload while pending and the cleaned copy once ready."""

    __tablename__ = "media"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    post_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    storage_key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(SmallInteger)
    height: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
