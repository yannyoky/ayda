import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.ids import uuid7
from ayda.core.models import module_metadata


class Base(DeclarativeBase):
    metadata = module_metadata("social")


class Post(Base):
    """A proof (friends visibility) or a routine entry; personal quests never create one."""

    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    day_quest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    kind: Mapped[str] = mapped_column(Text)
    quest_title: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(String(500))
    local_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Media(Base):
    """A photo, video or circle (`kind`). `storage_key` is the upload while pending, the
    cleaned copy once ready and empty once a video expired."""

    __tablename__ = "media"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    post_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Post.id))
    kind: Mapped[str] = mapped_column(Text, default="photo")
    storage_key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(SmallInteger)
    height: Mapped[int | None] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    inviter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Friendship(Base):
    """Stored once per pair: `user_low` < `user_high`."""

    __tablename__ = "friendships"

    user_low: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_high: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Like(Base):
    __tablename__ = "likes"

    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Post.id), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Post.id))
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    text: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
