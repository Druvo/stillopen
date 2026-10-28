"""Calendar downloads for interviews (.ics). Plain files, not JSON, so they live next to the other downloads and not under /api/v1/."""
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import CalendarFeed, Interview
from .services import calendarfeed, ics
from .services.throttle import throttled_ip


def _response(body: str, filename: str) -> HttpResponse:
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def interview_calendar(request, pk):
    """One interview of the signed-in person. Anyone else's is a 404."""
    item = get_object_or_404(Interview.objects.select_related("application"), pk=pk, owner=request.user)
    company = re.sub(r"[^A-Za-z0-9._-]+", "-", item.application.company).strip("-")[:40] or "interview"
    return _response(ics.calendar([item], name=ics.summary(item)), f"interview-{company}-{item.pk}.ics")


@login_required
@require_GET
def interviews_calendar(request):
    """Every interview of the signed-in person that has not happened yet and is still pending."""
    items = (
        Interview.objects.filter(owner=request.user, outcome="pending", scheduled_at__gte=timezone.now())
        .select_related("application").order_by("scheduled_at", "id")
    )
    return _response(ics.calendar(list(items)), "stillopen-interviews.ics")


# The private subscribable link: no sign-in -- the long random token in the address is the key. Read-only, rate-limited per visitor
# address, never indexed, and an unknown or revoked token is a plain 404.
@require_GET
def calendar_feed(request, token: str):
    if throttled_ip(request, "calfeed", settings.STILLOPEN_CALENDAR_FEED_PER_HOUR):
        response = HttpResponse("Too many requests. Try again later.", status=429, content_type="text/plain")
        response["Retry-After"] = "3600"
        return response
    feed = CalendarFeed.lookup(token)
    if feed is None:
        # guessing is slow: unknown links count against a much smaller allowance
        if throttled_ip(request, "calfeed-bad", settings.STILLOPEN_CALENDAR_FEED_BAD_PER_HOUR):
            return HttpResponse("Too many requests. Try again later.", status=429, content_type="text/plain")
        raise Http404("Not found.")
    now = timezone.now()
    if feed.last_used_at is None or (now - feed.last_used_at).total_seconds() > 300:
        CalendarFeed.objects.filter(pk=feed.pk).update(last_used_at=now)
    body = calendarfeed.build(feed.owner, now)
    tag = calendarfeed.etag(body)
    if request.headers.get("If-None-Match") == tag:
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'inline; filename="stillopen.ics"'
    response["ETag"] = tag
    # the address is a secret: keep it out of shared caches, search engines and Referer headers
    response["Cache-Control"] = "private, max-age=900"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response
