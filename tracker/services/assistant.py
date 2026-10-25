"""Rules for a person's assistant tokens, shared by the classic page and the JSON API. The raw token is returned once, by `ApiToken.issue`."""
from django.conf import settings
from django.utils import timezone

from ..models import ApiToken


class TokenRefused(Exception):
    """Nothing was made. `status` is the HTTP status the API uses."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def active_count(user) -> int:
    return sum(1 for t in user.api_tokens.all() if t.is_usable)


def check_room(user) -> None:
    active = active_count(user)
    if active >= settings.STILLOPEN_MAX_API_TOKENS:
        raise TokenRefused(f"You already have {active} active tokens. Revoke one you no longer use first.")


def parse_days(value) -> int:
    """The expiry in days; anything that is not one of the offered choices means 90."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 90
    return days if days in dict(ApiToken.EXPIRY_CHOICES) else 90


def revoke(token: ApiToken) -> None:
    if not token.revoked_at:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
