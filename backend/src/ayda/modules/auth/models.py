import uuid
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.ids import uuid7
from ayda.core.models import module_metadata


class Base(DeclarativeBase):
    metadata = module_metadata("auth")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    city_id: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'Europe/Moscow'"))
    theme: Mapped[str] = mapped_column(Text, server_default=text("'graphite'"))
    morning_reminder_at: Mapped[time | None] = mapped_column(Time)
    evening_reminder_at: Mapped[time | None] = mapped_column(Time)
    bot_reachable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # `auto`: push when the user has a device with the app, otherwise the bot.
    notification_channel: Mapped[str] = mapped_column(Text, server_default=text("'auto'"))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Access tokens issued before this moment are refused ("sign out everywhere").
    sessions_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserIdentity(Base):
    """A way to sign in: `telegram` (subject = Telegram user id) or `email` (normalized)."""

    __tablename__ = "identities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailCode(Base):
    __tablename__ = "email_codes"

    email_key: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailSend(Base):
    __tablename__ = "email_sends"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email_key: Mapped[bytes] = mapped_column(LargeBinary)
    client_key: Mapped[bytes] = mapped_column(LargeBinary)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramLoginRequest(Base):
    """A pending sign-in (or Telegram linking) from a native app, confirmed in the bot."""

    __tablename__ = "telegram_login_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    secret_hash: Mapped[bytes] = mapped_column(LargeBinary)
    client_key: Mapped[bytes] = mapped_column(LargeBinary)
    link_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Device(Base):
    """A phone with the native app that receives push notifications (FCM token)."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(Text)
    token: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
