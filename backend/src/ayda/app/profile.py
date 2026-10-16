from datetime import UTC, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import City, Me, ProfileUpdate, Reminders
from ayda.core.problems import Problem
from ayda.modules import auth, events


def format_local_time(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def parse_local_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def city_schema(city: events.City) -> City:
    return City(id=city.id, name=city.name, region_name=city.region_name, timezone=city.timezone)


async def build_me(session: AsyncSession, user: auth.User) -> Me:
    city = await events.get_city(session, user.city_id) if user.city_id is not None else None
    return Me(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        avatar_url=user.avatar_url,
        city=city_schema(city) if city else None,
        timezone=user.timezone,
        theme="plum" if user.theme == "plum" else "graphite",
        reminders=Reminders(
            morning_at=format_local_time(user.morning_reminder_at),
            evening_at=format_local_time(user.evening_reminder_at),
        ),
        consent_required=await auth.consent_required(session, user.id),
        onboarded=user.onboarded_at is not None,
    )


async def update_profile(session: AsyncSession, user: auth.User, update: ProfileUpdate) -> None:
    fields = update.model_fields_set
    if not fields:
        raise Problem(422, "validation-failed", detail="Нужно хотя бы одно поле")
    if "city_id" in fields:
        if update.city_id is None:
            raise Problem(422, "validation-failed", detail="Город нельзя убрать")
        city = await events.get_city(session, update.city_id)
        if city is None:
            raise Problem(422, "unknown-city", detail="Такого города нет в списке")
        # Only the city is stored; the time zone follows it.
        user.city_id = city.id
        user.timezone = city.timezone
    if "theme" in fields and update.theme is not None:
        user.theme = update.theme
    if "reminders" in fields and update.reminders is not None:
        user.morning_reminder_at = parse_local_time(update.reminders.morning_at)
        user.evening_reminder_at = parse_local_time(update.reminders.evening_at)


async def complete_onboarding(session: AsyncSession, user: auth.User) -> None:
    if await auth.consent_required(session, user.id) is not None:
        raise Problem(409, "consent-required", detail="Сначала нужно принять согласие")
    if user.city_id is None:
        raise Problem(409, "city-required", detail="Сначала выберите город")
    if user.onboarded_at is None:
        user.onboarded_at = datetime.now(UTC)
