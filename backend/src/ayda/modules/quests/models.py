import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ayda.core.ids import uuid7
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


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    local_date: Mapped[date] = mapped_column(Date)
    # Visible only to its author; never logged; set to null after 30 days.
    text: Mapped[str | None] = mapped_column(String(1000))
    mood: Mapped[str] = mapped_column(Text)
    parsed: Mapped[dict[str, Any]] = mapped_column(JSONB)
    submissions: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DayPool(Base):
    __tablename__ = "day_pools"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    local_date: Mapped[date] = mapped_column(Date)
    checkin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(Checkin.id))
    status: Mapped[str] = mapped_column(Text)
    ranked_by: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    weather: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    replacements_used: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DayQuest(Base):
    __tablename__ = "day_quests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    pool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DayPool.id))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    local_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(ForeignKey(Template.id))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    outdoor: Mapped[bool] = mapped_column(Boolean)
    why: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)
    state: Mapped[str] = mapped_column(Text)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str | None] = mapped_column(Text)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PointsEntry(Base):
    """Append-only: a row is never updated or deleted, so points stay when a post goes."""

    __tablename__ = "points_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    day_quest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DayQuest.id))
    # 'quest' (one per completed quest) or 'coop_bonus' (one per quest of a finished co-op)
    kind: Mapped[str] = mapped_column(Text, default="quest")
    local_date: Mapped[date] = mapped_column(Date)
    week_start: Mapped[date] = mapped_column(Date)
    points: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Streak(Base):
    __tablename__ = "streaks"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    current_days: Mapped[int] = mapped_column(Integer)
    best_days: Mapped[int] = mapped_column(Integer)
    last_counted_date: Mapped[date | None] = mapped_column(Date)
    freeze_week_start: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Coop(Base):
    """A co-op quest (US-18): the owner's taken quest that friends do too, each on their own."""

    __tablename__ = "coops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    outdoor: Mapped[bool] = mapped_column(Boolean)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bonus_awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CoopParticipant(Base):
    __tablename__ = "coop_participants"

    coop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(Coop.id), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # 'owner', 'invited', 'accepted' or 'declined'
    status: Mapped[str] = mapped_column(Text)
    day_quest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(DayQuest.id))
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
