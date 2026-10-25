"""What is coming up for one person, in one place: the dashboard's "Coming up" card and the weekly "what to do this week" email read the
same list. Nothing here changes a job and nothing leaves the person's own data."""
from datetime import date, datetime, time, timedelta

from django.core.mail import send_mail
from django.utils import timezone

from tracker.models import Application, Interview, Offer, ScoreBand, SiteConfig, UserProfile
from tracker.services import apply as apply_service
from tracker.services import integrations, links, stats, tz

COMING_UP_DAYS = 14
WEEK_DAYS = 7
MIN_DAYS_BETWEEN = 6  # nobody gets the weekly email twice in this many days
STRONG_DEFAULT_PERCENT = 70
KIND_WORDS = {"interview": "Interview", "deadline": "Apply by", "offer": "Reply to the offer by"}


def coming_up(user, days: int = COMING_UP_DAYS, today: date | None = None, now: datetime | None = None) -> list[dict]:
    """Interviews, job deadlines and offer reply-by dates in the next `days` days, soonest first.

    Each item: {kind: "interview" | "deadline" | "offer", date (YYYY-MM-DD, the person's own calendar), when (ISO date, or ISO time for an
    interview), label, company, role, job_id}. Deadlines of jobs at a terminal status (closed, rejected...) are left out, and so are
    offers that were already accepted or declined."""
    zone = tz.zone_for(user)
    now = now or timezone.now()
    today = today or now.astimezone(zone).date()
    last = today + timedelta(days=days)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone)
    items = []
    for i in Interview.objects.filter(owner=user, outcome="pending", scheduled_at__gte=now, scheduled_at__lt=end).select_related("application").order_by("scheduled_at"):
        local = i.scheduled_at.astimezone(zone)
        items.append({
            "kind": "interview", "date": local.date().isoformat(), "when": i.scheduled_at.isoformat(), "label": i.get_kind_display(),
            "company": i.application.company, "role": i.application.role, "job_id": i.application_id, "_sort": local.replace(tzinfo=None),
        })
    for a in Application.objects.filter(owner=user, deadline__gte=today, deadline__lte=last, status__is_terminal=False):
        items.append({
            "kind": "deadline", "date": a.deadline.isoformat(), "when": a.deadline.isoformat(), "label": KIND_WORDS["deadline"],
            "company": a.company, "role": a.role, "job_id": a.pk, "_sort": datetime.combine(a.deadline, time.min),
        })
    for o in Offer.objects.filter(owner=user, status="open", deadline__gte=today, deadline__lte=last).select_related("application"):
        items.append({
            "kind": "offer", "date": o.deadline.isoformat(), "when": o.deadline.isoformat(), "label": KIND_WORDS["offer"],
            "company": o.application.company, "role": o.application.role, "job_id": o.application_id, "_sort": datetime.combine(o.deadline, time.min),
        })
    items.sort(key=lambda item: (item["_sort"], item["kind"]))
    for item in items:
        del item["_sort"]
    return items


def new_strong_matches(user, today: date, limit: int = 5, days: int = WEEK_DAYS) -> list[Application]:
    """The best jobs added in the last `days` days whose match is in the top score band (or at least 70% when no bands are set)."""
    config = SiteConfig.for_user(user)
    bands = list(ScoreBand.objects.all())
    threshold = bands[0].min_percent if bands else STRONG_DEFAULT_PERCENT
    since = today - timedelta(days=days - 1)
    rows = []
    for app in Application.objects.filter(owner=user, found_date__gte=since, status__is_terminal=False).select_related("status"):
        percent = app.match_percent(config.score_scale)
        if percent is not None and percent >= threshold:
            rows.append((percent, app))
    rows.sort(key=lambda row: (-row[0], row[1].pk))
    return [app for _, app in rows[:limit]]


def _on(day: str) -> str:
    return f"{date.fromisoformat(day):%a %d %b}"


def week_content(user, today: date | None = None, now: datetime | None = None) -> dict:
    """Everything the weekly email would say. `empty` is True when there is nothing worth an email."""
    now = now or timezone.now()
    today = today or tz.today_for(user)
    numbers = stats.candidate_stats(user, today)
    ahead = coming_up(user, WEEK_DAYS, today, now)
    followups = list(apply_service.due_followups(user, today))
    matches = new_strong_matches(user, today)
    waiting = numbers["waiting"]["longest"][:3]
    empty = not (followups or ahead or matches or waiting)
    return {
        "summary": numbers["summary_text"], "followups": followups, "ahead": ahead, "matches": matches, "waiting": waiting,
        "empty": empty or not numbers["has_jobs"], "today": today,
    }


def weekly_text(user, content: dict) -> str:
    today = content["today"]
    lines = ["Your week on StillOpen", "", content["summary"], ""]
    if content["followups"]:
        lines.append("Follow-ups due:")
        for a in content["followups"]:
            late = (today - a.follow_up_date).days
            when = "today" if late <= 0 else f"{late} day{'s' if late != 1 else ''} overdue"
            link = links.job_link(a.pk)
            lines.append(f"- {a.company} - {a.role} ({when})" + (f"\n  {link}" if link else ""))
        lines.append("")
    interviews = [i for i in content["ahead"] if i["kind"] == "interview"]
    if interviews:
        lines.append("Interviews in the next 7 days:")
        for i in interviews:
            when = datetime.fromisoformat(i["when"]).astimezone(tz.zone_for(user))
            lines.append(f"- {when:%a %d %b, %H:%M}: {i['label']} for {i['company']} - {i['role']}")
        link = links.app_url("/interviews")
        if link:
            lines.append(f"  {link}")
        lines.append("")
    dates = [i for i in content["ahead"] if i["kind"] != "interview"]
    if dates:
        lines.append("Dates to keep in mind:")
        for i in dates:
            what = "reply to the offer from" if i["kind"] == "offer" else "apply to"
            lines.append(f"- {_on(i['date'])}: {what} {i['company']} - {i['role']}" + (" (your reply date)" if i["kind"] == "offer" else " (last day)"))
            link = links.job_link(i["job_id"]) if i["kind"] == "deadline" else links.app_url("/offers")
            if link:
                lines.append(f"  {link}")
        lines.append("")
    if content["matches"]:
        lines.append("New strong matches this week:")
        for a in content["matches"]:
            lines.append(f"- {a.company} - {a.role}")
            link = links.job_link(a.pk)
            if link:
                lines.append(f"  {link}")
        lines.append("")
    if content["waiting"]:
        lines.append("Waiting longest for a reply:")
        for w in content["waiting"]:
            lines.append(f"- {w['company']} - {w['role']} ({w['days']} days)")
        lines.append("")
    lines.append(links.link_line("Open your dashboard", "/", "your dashboard"))
    lines.append(links.CHANGE_LINE)
    return "\n".join(lines)


def send_weekly_summary(owner, now: datetime | None = None) -> str:
    """Send this person's weekly email. Returns "sent", or why not: "recent" (sent in the last 6 days), "no_address" (no verified address)
    or "nothing" (nothing to say). The person's own tick and the admin's switch are checked by the caller."""
    now = now or timezone.now()
    profile = UserProfile.for_user(owner)
    if profile.weekly_emailed_at and now - profile.weekly_emailed_at < timedelta(days=MIN_DAYS_BETWEEN):
        return "recent"
    if not links.verified_address(owner):
        return "no_address"
    content = week_content(owner, now=now)
    if content["empty"]:
        return "nothing"
    send_mail(
        subject="StillOpen: your week",
        message=weekly_text(owner, content),
        from_email=integrations.from_email(),
        recipient_list=[owner.email],
        fail_silently=False,
    )
    profile.weekly_emailed_at = now
    profile.save(update_fields=["weekly_emailed_at"])
    return "sent"
