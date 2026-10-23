"""Pydantic models mirroring contracts/openapi.yaml components (ADR 0004)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Theme = Literal["graphite", "plum"]
NotificationChannel = Literal["auto", "push", "telegram"]
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
    notification_channel: NotificationChannel = "auto"


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


class TelegramLoginRequestOut(BaseModel):
    id: uuid.UUID
    poll_secret: str
    bot_url: str
    expires_at: datetime


class TelegramLoginExchange(BaseModel):
    poll_secret: str = Field(max_length=128)


class SignInIdentity(BaseModel):
    id: uuid.UUID
    provider: Literal["telegram", "email"]
    label: str
    created_at: datetime


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
    notification_channel: NotificationChannel | None = None


class DeviceIn(BaseModel):
    platform: Literal["android", "ios"]
    token: str = Field(min_length=1, max_length=4096)


class Device(BaseModel):
    id: uuid.UUID
    platform: Literal["android", "ios"]
    created_at: datetime


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


class Place(BaseModel):
    """A snapshot of a venue, so a plan stays stable if its source changes (ADR 0010)."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    address: Annotated[str, StringConstraints(max_length=200)] | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    link: Annotated[str, StringConstraints(pattern=r"^https://", max_length=500)] | None = None
    source: Annotated[str, StringConstraints(max_length=32)] | None = None
    source_id: Annotated[str, StringConstraints(max_length=64)] | None = None
    price_hint: Annotated[str, StringConstraints(max_length=40)] | None = None


ItemText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class CoopPartInput(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    category: Category | None = None
    duration_min: int | None = Field(default=None, ge=5, le=480)
    assignee_id: uuid.UUID
    place: Place | None = None
    starts_at: datetime | None = None
    opens_after: int | None = Field(default=None, ge=0)
    items: list[ItemText] = Field(default_factory=lambda: [], max_length=20)


class CoopCreateInput(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    category: Category
    duration_min: int = Field(ge=5, le=480)
    outdoor: bool = False
    place: Place | None = None
    starts_at: datetime | None = None
    friend_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)
    parts: list[CoopPartInput] | None = Field(default=None, min_length=2, max_length=5)


class CoopItemInput(BaseModel):
    done: bool


class HandoffInput(BaseModel):
    friend_id: uuid.UUID


class CoopParticipant(BaseModel):
    user: UserSummary
    status: CoopStatus
    completed: bool


class CoopItem(BaseModel):
    id: uuid.UUID
    text: str
    done: bool


class CoopHandoffOffer(BaseModel):
    to: UserSummary
    for_me: bool


class CoopPart(BaseModel):
    id: uuid.UUID
    position: int
    title: str
    category: Category
    duration_min: int
    place: Place | None
    starts_at: datetime | None
    assignee: UserSummary
    state: Literal["locked", "open", "done"]
    opens_after: uuid.UUID | None
    items: list[CoopItem]
    my_quest_id: uuid.UUID | None
    handoff: CoopHandoffOffer | None


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
    kind: Literal["same", "parts"] = "same"
    place: Place | None = None
    starts_at: datetime | None = None
    parts: list[CoopPart] | None = None


class MeetupVenue(BaseModel):
    id: int
    name: str
    kind: Literal["restaurant", "cafe", "bar", "pub", "fast_food"]
    address: str | None
    distance_m: int
    opening_hours: str | None
    open_now: bool | None
    osm_url: str
    gis_url: str
    yandex_url: str


class MeetupOffer(BaseModel):
    kind: Literal["venue", "online", "unclear"]
    source: Literal["llm", "code"]
    starts_at: datetime | None
    activity: str | None
    venues: list[MeetupVenue]
    note: str | None
    attribution: str | None


class MeetupPick(BaseModel):
    """Either a venue from the offer, or an online activity."""

    venue_id: int | None = None
    activity: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] | None
    ) = None
    starts_at: datetime


Meal = Literal["breakfast", "lunch", "dinner", "snack", "dessert"]
Allergen = Literal["gluten", "milk", "egg", "fish", "shellfish", "nuts", "peanut", "soy", "sesame"]


class RecipeSuggestInput(BaseModel):
    meal: Meal | None = None
    max_minutes: int | None = Field(default=None, ge=10, le=240)
    allergens: list[Allergen] = Field(default_factory=lambda: [], max_length=9)
    vegetarian: bool = False


class RecipeCard(BaseModel):
    id: str
    title: str
    meal: Meal
    minutes: int
    servings: int
    allergens: list[Allergen]
    vegetarian: bool
    why: str | None


class RecipeOffer(BaseModel):
    source: Literal["llm", "code"]
    recipes: list[RecipeCard]
    note: str | None


class RecipeLine(BaseModel):
    ingredient: str
    name: str
    amount: float
    unit: Literal["g", "ml", "pcs", "clove", "slice", "tbsp", "tsp", "pinch"]
    aisle: Literal[
        "produce", "dairy", "meat", "fish", "grocery", "bakery", "frozen", "drinks", "other"
    ]
    optional: bool
    staple: bool


class RecipeDetail(BaseModel):
    recipe: RecipeCard
    servings: int
    lines: list[RecipeLine]
    steps: list[str]
    note: str


class RecipePlanInput(BaseModel):
    friend_id: uuid.UUID
    shopper: Literal["me", "friend"]
    servings: int = Field(default=2, ge=1, le=8)
    at_home: list[Annotated[str, StringConstraints(max_length=40)]] = Field(
        default_factory=lambda: [], max_length=60
    )
    starts_at: datetime | None = None
