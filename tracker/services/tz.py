"""Per-person time zone: "today" is the person's today, not the server's.

`UserProfile.timezone` is an IANA name such as "Asia/Dhaka"; blank means the site's TIME_ZONE (so a person who never
sets it sees exactly what they saw before). Everything that turns a moment into a calendar day for a person (the prep
streak, today's practice, follow-ups due, deadlines "in 3 days", the greeting, "this week" in the stats) goes through
`today_for` / `now_for`.
"""
from __future__ import annotations

import datetime as dt
import functools
from zoneinfo import ZoneInfo, available_timezones

from django.core.exceptions import ValidationError
from django.utils import timezone

# A short list for the profile picker; the full IANA list is offered too (see `all_zones`).
COMMON_ZONES = [
    "UTC", "Asia/Dhaka", "Asia/Kolkata", "Asia/Karachi", "Asia/Dubai", "Asia/Riyadh", "Asia/Kuala_Lumpur", "Asia/Singapore",
    "Asia/Manila", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney", "Pacific/Auckland", "Europe/London", "Europe/Berlin",
    "Europe/Paris", "Europe/Istanbul", "Africa/Cairo", "Africa/Lagos", "Africa/Nairobi", "America/Sao_Paulo",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Toronto",
]


@functools.lru_cache(maxsize=1)
def all_zones() -> list[str]:
    return sorted(z for z in available_timezones() if "/" in z or z == "UTC")


def is_valid(name: str) -> bool:
    """True for a real IANA zone name. Blank is valid (it means the site's zone)."""
    name = (name or "").strip()
    if not name:
        return True
    if name not in all_zones():
        return False
    try:
        ZoneInfo(name)
    except Exception:  # noqa: BLE001 - a name that exists in the list but cannot load (broken tzdata)
        return False
    return True


def validate_timezone(value: str) -> None:
    if not is_valid(value):
        raise ValidationError("That is not a time zone we know. Pick one from the list, for example Asia/Dhaka or America/Los_Angeles.")


def _name_for(user_id: int) -> str:
    from ..models import UserProfile  # imported late: models import this module for the field validator

    return UserProfile.objects.filter(user_id=user_id).values_list("timezone", flat=True).first() or ""


def zone_for(user) -> dt.tzinfo:
    """The person's own zone, or the site's when they have not set one (or it can no longer be loaded).

    `user` may be a User, a user id, or None. One small query per call, so a request that needs the date several times asks once and passes it on."""
    name = ""
    if isinstance(user, int):
        name = _name_for(user)
    elif user is not None and getattr(user, "pk", None):
        name = _name_for(user.pk)
    return zone_from_name(name)


def zone_from_name(name: str) -> dt.tzinfo:
    if name:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 - never break a page over a zone name
            pass
    return timezone.get_default_timezone()


def now_for(user) -> dt.datetime:
    """The current moment as a timezone-aware datetime in the person's zone."""
    return timezone.now().astimezone(zone_for(user))


def today_for(user) -> dt.date:
    """The person's calendar date right now."""
    return now_for(user).date()


def local_date(moment: dt.datetime | None, user) -> dt.date | None:
    """The person's calendar date for a stored moment (None stays None)."""
    if moment is None:
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.get_default_timezone())
    return moment.astimezone(zone_for(user)).date()
