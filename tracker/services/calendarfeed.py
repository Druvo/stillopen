"""What a person's subscribable calendar link (/calendar/<token>.ics) says, and how the link is made and revoked.

Only dates leave here: upcoming interviews, follow-up days and apply-by days, each titled with company and role. Never a job
description, a note, a meeting link, a contact or a score -- the link is a secret URL that anyone holding it can read."""
import hashlib
from datetime import timedelta

from django.utils import timezone

from tracker.models import Application, CalendarFeed, Interview

from . import ics

MAX_EVENTS = 200  # per kind; a calendar app does not need more than this


def issue(user):
    return CalendarFeed.issue(user)


def revoke(user) -> bool:
    return CalendarFeed.objects.filter(owner=user).delete()[0] > 0


def url_for(request, feed: CalendarFeed) -> str:
    return request.build_absolute_uri(f"/calendar/{feed.token}.ics")


def _title(app: Application) -> str:
    return f"{app.company} - {app.role}" if app.company else app.role


def build(user, now=None) -> str:
    """The iCalendar text for `user`'s own rows only."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    events: list[list[str]] = []
    interviews = (
        Interview.objects.filter(owner=user, scheduled_at__gte=now - timedelta(hours=2)).exclude(outcome__in=("cancelled", "rejected"))
        .select_related("application").order_by("scheduled_at")[:MAX_EVENTS]
    )
    for i in interviews:
        events.append(ics.event_lines(i, now, private=True))
    open_jobs = Application.objects.filter(owner=user).exclude(status__is_terminal=True)
    for a in open_jobs.filter(follow_up_date__gte=today).order_by("follow_up_date")[:MAX_EVENTS]:
        events.append(ics.day_event_lines(f"followup-{a.pk}@stillopen", f"Follow up: {_title(a)}", a.follow_up_date, now))
    for a in open_jobs.filter(deadline__gte=today, applied_date__isnull=True).order_by("deadline")[:MAX_EVENTS]:
        events.append(ics.day_event_lines(f"deadline-{a.pk}@stillopen", f"Apply by: {_title(a)}", a.deadline, now))
    return ics.wrap("StillOpen: my job search", events, subscribed=True)


def etag(body: str) -> str:
    """Same dates, same tag -- DTSTAMP is left out so a poll that finds nothing new can be answered with 304."""
    stable = "\n".join(line for line in body.splitlines() if not line.startswith("DTSTAMP:"))
    return '"' + hashlib.sha256(stable.encode()).hexdigest()[:32] + '"'
