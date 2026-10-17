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
    refresh_token: str | None = None
    refresh_expires_at: datetime | None = None
    user: Me


class EmailStart(BaseModel):
    email: str = Field(max_length=254)


class EmailVerify(BaseModel):
    email: str = Field(max_length=254)
    code: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class RefreshTokenInput(BaseModel):
    refresh_token: str = Field(max_length=256)


class TelegramSignIn(BaseModel):
    init_data: str = Field(max_length=4096)


class UserSummary(BaseModel):
    id: uuid.UUID
    first_name: str
    avatar_url: str | None = None


class ProfileUpdate(BaseModel):
    first_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None
    ) = None
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
QuestSource = Literal["catalog", "checkin_task", "custom", "coop", "event"]
PoolStatus = Literal["none", "generating", "ready", "failed"]
Condition = Literal["clear", "cloudy", "rain", "snow", "storm", "unknown"]


class CheckinInput(BaseModel):
    text: str = Field(default="", max_length=1000)
    mood: Mood


class Checkin(BaseModel):
    text: str
    mood: Mood
    submitted_at: datetime


class EventInfo(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime | None
    venue: str | None
    address: str | None
    city: str | None
    is_free: bool
    price_min: int | None
    url: str
    source: Literal["timepad", "kudago", "culture"]


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
    coop_id: uuid.UUID | None = None
    event: EventInfo | None = None


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
    coop_bonus: int = 0


class Invite(BaseModel):
    code: str
    url: str
    expires_at: datetime


class Friend(UserSummary):
    since: datetime


class Photo(BaseModel):
    id: uuid.UUID
    url: str
    width: int
    height: int


class Post(BaseModel):
    id: uuid.UUID
    author: UserSummary
    kind: Literal["proof", "routine"]
    quest_title: str | None
    category: Category
    caption: str | None
    photos: list[Photo]
    local_date: date
    created_at: datetime
    like_count: int
    liked_by_me: bool
    comment_count: int


class PostPage(BaseModel):
    items: list[Post]
    next_cursor: str | None


class LikeState(BaseModel):
    like_count: int
    liked_by_me: bool


class CommentInput(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Comment(BaseModel):
    id: uuid.UUID
    author: UserSummary
    text: str
    created_at: datetime
    can_delete: bool


class CommentPage(BaseModel):
    items: list[Comment]
    next_cursor: str | None


class LadderEntry(BaseModel):
    rank: int
    user: UserSummary
    points: int
    streak_days: int
    is_me: bool


class Ladder(BaseModel):
    week_start: date
    entries: list[LadderEntry]


class RealtimeToken(BaseModel):
    token: str
    expires_at: datetime
    url: str
    channel: str


class Message(BaseModel):
    id: int
    conversation_id: uuid.UUID
    author: UserSummary
    text: str
    created_at: datetime
    client_id: uuid.UUID | None


class MessageInput(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    client_id: uuid.UUID


class MessagePage(BaseModel):
    items: list[Message]
    next_cursor: str | None


class Conversation(BaseModel):
    id: uuid.UUID
    kind: Literal["dm", "coop"]
    title: str
    peer: UserSummary | None
    coop_id: uuid.UUID | None
    members: list[UserSummary]
    can_send: bool
    last_message: Message | None
    unread_count: int
    last_read_message_id: int | None
    updated_at: datetime


class DirectConversationInput(BaseModel):
    user_id: uuid.UUID


class ReadInput(BaseModel):
    last_read_message_id: int = Field(ge=0)


CoopStatus = Literal["owner", "invited", "accepted", "declined"]


class CoopInput(BaseModel):
    friend_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


class CoopParticipant(BaseModel):
    user: UserSummary
    status: CoopStatus
    completed: bool


class Coop(BaseModel):
    id: uuid.UUID
    title: str
    category: Category
    duration_min: int
    owner: UserSummary
    my_status: CoopStatus
    participants: list[CoopParticipant]
    my_quest_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    expires_at: datetime
    bonus_awarded: bool
