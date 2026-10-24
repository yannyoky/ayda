import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.ids import uuid7
from ayda.core.models import module_metadata


class Base(DeclarativeBase):
    metadata = module_metadata("chat")


class Conversation(Base):
    """A direct chat of two friends (`dm`) or the chat of a co-op quest (`coop`)."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(Text)
    dm_key: Mapped[str | None] = mapped_column(Text, unique=True)
    coop_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Member(Base):
    __tablename__ = "members"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Conversation.id), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_read_message_id: Mapped[int | None] = mapped_column(BigInteger)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # "Удалить у себя": the chat and its older messages are gone for this member; a newer
    # message brings the chat back with only what came after.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Conversation.id))
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    text: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attachment(Base):
    """A voice message (ADR 0019): uploaded straight to storage, then re-encoded by the
    worker. The original upload is deleted; only the cleaned copy is ever shown."""

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Conversation.id, ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey(Message.id, ondelete="CASCADE"), unique=True
    )
    kind: Mapped[str] = mapped_column(Text)
    # pending (not sent yet) -> processing -> ready | failed
    status: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
