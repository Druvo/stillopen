"""Adding a company job board to a person's own search. One place for the rules, used by the classic page and the JSON API.

The person supplies only a connector from the fixed list and a short name; the app builds the real URL itself and the first
fetch goes through the guarded `scan._fetch`. Caps and the hourly limit come from settings."""
from typing import Callable

from django.conf import settings
from django.db import IntegrityError, transaction

from ..models import JobSource, SiteConfig
from . import scan
from .netguard import FetchError


class SourceRefused(Exception):
    """Nothing was added. `info` is True when it is a plain "nothing to do" rather than a problem; `status` is the HTTP status the API uses."""

    def __init__(self, message: str, info: bool = False, status: int = 400):
        super().__init__(message)
        self.info = info
        self.status = status


def add_own_source(user, connector: str, token: str, name: str, rate_limited: Callable[[], bool]) -> tuple[JobSource, int]:
    """Check, read once to prove it works, and save. Returns (source, openings seen). Raises `SourceRefused` with words for the person."""
    if JobSource.objects.filter(owner=user).count() >= settings.STILLOPEN_MAX_OWN_SOURCES:
        raise SourceRefused(f"You can add up to {settings.STILLOPEN_MAX_OWN_SOURCES} boards. Remove one first.")
    if JobSource.objects.filter(owner__isnull=True, connector=connector, board_token=token).exists():
        raise SourceRefused("That company is already part of every search, so there is nothing to add.", info=True)
    if JobSource.objects.filter(owner=user, connector=connector, board_token=token).exists():
        raise SourceRefused("You already added that board.", info=True)
    if rate_limited():
        raise SourceRefused("You have added a lot of boards this hour. Try again later.", status=429)
    try:
        openings = scan._fetch(connector, token)  # the same guarded fetch a scan uses: fixed host, no redirects to private addresses
    except (FetchError, KeyError, ValueError):
        raise SourceRefused("We could not read jobs from that board. Check the name against the company's careers page address and try again.") from None
    try:
        with transaction.atomic():
            source = JobSource.objects.create(owner=user, name=name[:120], connector=connector, board_token=token)
    except IntegrityError:
        raise SourceRefused("You already added that board.", info=True) from None
    return source, len(openings)


def shared_sources():
    """The site-wide sources that really are searched: Jooble ones only count once the site has a Jooble key."""
    qs = JobSource.objects.filter(owner__isnull=True, enabled=True)
    return qs if SiteConfig.load().effective_jooble_key else qs.exclude(connector="jooble")
