"""The user's local day starts at 04:00 local time: late evenings belong to the day before."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DAY_STARTS_AT = time(4, 0)


def local_now(now: datetime, tz: str) -> datetime:
    return now.astimezone(ZoneInfo(tz))


def local_day(now: datetime, tz: str) -> date:
    """Calendar date of the current quest day in the user's time zone."""
    return (local_now(now, tz) - timedelta(hours=DAY_STARTS_AT.hour)).date()


def day_expires_at(day: date, tz: str) -> datetime:
    """04:00 local time on the next date, in UTC."""
    end = datetime.combine(day + timedelta(days=1), DAY_STARTS_AT, ZoneInfo(tz))
    return end.astimezone(UTC)


def week_start(day: date) -> date:
    """Monday of the week the day belongs to."""
    return day - timedelta(days=day.weekday())
