"""Pydantic models mirroring contracts/openapi.yaml components (ADR 0004)."""

import uuid
from datetime import datetime
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
