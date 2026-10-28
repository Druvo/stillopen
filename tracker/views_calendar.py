"""The private calendar link: GET /calendar/<token>.ics. No sign-in -- the long random token in the address is the key, so this is
read-only, rate-limited per visitor address, never indexed, and answers an unknown or revoked token with a plain 404."""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import CalendarFeed
from .services import calendarfeed
from .services.throttle import throttled_ip


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
