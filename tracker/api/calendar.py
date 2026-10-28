"""The person's private calendar link, for the Interviews screen. The link is a secret address (see `views_calendar.py`): it is shown only
to its owner, making a new one replaces the old one at once, and turning it off deletes it."""
from django.conf import settings
from django.http import JsonResponse
from ninja import Router

from ..models import CalendarFeed
from ..services import calendarfeed
from .common import throttle

router = Router()


def _state(request, feed) -> JsonResponse:
    data = {
        "enabled": feed is not None, "url": calendarfeed.url_for(request, feed) if feed else "",
        "created_at": feed.created_at.isoformat() if feed else None, "last_used_at": feed.last_used_at.isoformat() if feed and feed.last_used_at else None,
    }
    response = JsonResponse(data)
    response["Cache-Control"] = "no-store"
    return response


@router.get("/calendar-link", summary="The person's private calendar link, if they made one")
def get_link(request):
    return _state(request, CalendarFeed.objects.filter(owner=request.user).first())


@router.post("/calendar-link", summary="Make a calendar link, or replace it with a new one (the old one stops working)")
def make_link(request):
    throttle(request, "calendar-link", settings.STILLOPEN_CALENDAR_LINKS_PER_HOUR)
    feed, _ = calendarfeed.issue(request.user)
    return _state(request, feed)


@router.delete("/calendar-link", summary="Turn the calendar link off")
def delete_link(request):
    calendarfeed.revoke(request.user)
    return _state(request, None)
