"""Pydantic models mirroring contracts/openapi.yaml components (ADR 0004)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Theme = Literal["graphite", "plum"]
LocalTime = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class City(BaseModel):
    id: int
    name: str
    region_name: str
    timezone: str


class Reminders(BaseModel):
    morning_at: LocalTime | None
    evening_at: LocalTime | None


class Me(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    city: City | None = None
    timezone: str
    theme: Theme
    reminders: Reminders
    consent_required: str | None
    onboarded: bool


class Session(BaseModel):
    access_token: str
    expires_at: datetime
    user: Me


class TelegramSignIn(BaseModel):
    init_data: str = Field(max_length=4096)


class UserSummary(BaseModel):
    id: uuid.UUID
    first_name: str
    avatar_url: str | None = None


class ProfileUpdate(BaseModel):
    city_id: int | None = None
    theme: Theme | None = None
    reminders: Reminders | None = None


class ConsentInput(BaseModel):
    version: str = Field(max_length=32)


class Goal(BaseModel):
    code: str
    title: str


class GoalSelection(BaseModel):
    goal_codes: list[str] = Field(max_length=5)


class HabitCreate(BaseModel):
    direction: Literal["more", "less"]
    text: str = Field(min_length=1, max_length=100)


class Habit(HabitCreate):
    id: uuid.UUID


class Items[T](BaseModel):
    items: list[T]


Mood = Literal["energetic", "normal", "tired"]
Category = Literal["sport", "walk", "city", "rest", "project", "social", "home", "learning"]
Visibility = Literal["personal", "routine", "friends"]
RejectReason = Literal["no_time", "dont_want", "cant"]
QuestState = Literal["offered", "taken", "replaced", "completed", "expired"]
QuestSource = Literal["catalog", "checkin_task", "custom"]
PoolStatus = Literal["none", "generating", "ready", "failed"]
Condition = Literal["clear", "cloudy", "rain", "snow", "storm", "unknown"]


class CheckinInput(BaseModel):
    text: str = Field(default="", max_length=1000)
    mood: Mood


class Checkin(BaseModel):
    text: str
    mood: Mood
    submitted_at: datetime


class DayQuest(BaseModel):
    id: uuid.UUID
    source: QuestSource
    title: str
    description: str | None
    category: Category
    duration_min: int
    base_points: int
    why: str | None
    outdoor: bool
    state: QuestState
    visibility: Visibility | None
    points_awarded: int | None
    expires_at: datetime


class Weather(BaseModel):
    temperature_c: float
    condition: Condition


class Streak(BaseModel):
    current_days: int
    best_days: int
    freeze_available: bool


class DayLimits(BaseModel):
    taken: int
    max_taken: int
    replacements_left: int


class Day(BaseModel):
    local_date: date
    checkin: Checkin | None
    pool_status: PoolStatus
    weather: Weather | None
    quests: list[DayQuest]
    limits: DayLimits
    points_today: int
    points_week: int
    streak: Streak


class OwnQuestInput(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    category: Category
    duration_min: int = Field(ge=5, le=480)


class ReplaceInput(BaseModel):
    reason: RejectReason | None = None


class Replacement(BaseModel):
    replaced: DayQuest
    replacement: DayQuest | None
    replacements_left: int


class UploadInput(BaseModel):
    content_type: Literal["image/jpeg", "image/png", "image/heic", "image/webp"]
    size_bytes: int = Field(ge=1, le=10 * 1024 * 1024)


class UploadSlot(BaseModel):
    media_id: uuid.UUID
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime


class CompleteQuestInput(BaseModel):
    visibility: Visibility
    caption: str | None = Field(default=None, max_length=500)
    media_ids: list[uuid.UUID] = Field(default_factory=lambda: [], max_length=3)


class PointsBreakdown(BaseModel):
    base: int
    visibility_multiplier: float
    streak_multiplier: float


class Completion(BaseModel):
    quest: DayQuest
    points_awarded: int
    points_breakdown: PointsBreakdown
    streak: Streak
    post_id: uuid.UUID | None
