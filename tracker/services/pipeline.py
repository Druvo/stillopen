"""Interview reminder emails and the funnel numbers behind the Insights page. Nothing here changes a job."""
from datetime import timedelta
from statistics import median

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from tracker.models import Application, Interview
from tracker.services import integrations

REMINDER_HOURS = 24


def due_interview_reminders(owner, now=None, hours: int = REMINDER_HOURS):
    """Pending interviews starting within `hours` that this person has not been reminded about yet."""
    now = now or timezone.now()
    return list(
        Interview.objects.filter(
            owner=owner, outcome="pending", reminded_at__isnull=True,
            scheduled_at__gte=now, scheduled_at__lte=now + timedelta(hours=hours),
        ).select_related("application").order_by("scheduled_at")
    )


def reminder_text(items) -> str:
    lines = ["Interviews coming up on your StillOpen tracker:", ""]
    for i in items:
        when = timezone.localtime(i.scheduled_at)
        lines.append(f"- {when:%a %d %b, %H:%M}: {i.get_kind_display()} for {i.application.company} - {i.application.role}")
        if i.where:
            lines.append(f"  Where: {i.where}")
        if i.notes:
            lines.append(f"  Your notes: {i.notes[:300]}")
    lines += ["", "Good luck. Mark how it went on your Interviews page afterwards."]
    return "\n".join(lines)


def send_interview_reminders(owner, items) -> bool:
    """One email per person per run. Needs a verified address; nothing is marked as sent otherwise."""
    from allauth.account.models import EmailAddress

    if not items:
        return False
    if not EmailAddress.objects.filter(user=owner, email=owner.email, verified=True).exists():
        return False
    send_mail(
        subject=f"StillOpen: {len(items)} interview{'s' if len(items) != 1 else ''} in the next day",
        message=reminder_text(items),
        from_email=integrations.from_email(),
        recipient_list=[owner.email],
        fail_silently=False,
    )
    Interview.objects.filter(pk__in=[i.pk for i in items]).update(reminded_at=timezone.now())
    return True


def _days(start, end):
    return max(0, (end - start).days)


def funnel(owner) -> dict:
    """Plain counts for one person: how far their applications get, and what seems to work. Never a prediction."""
    apps = list(
        Application.objects.filter(owner=owner).select_related("status")
        .prefetch_related("interviews", "offers")
    )
    applied = [a for a in apps if a.applied_date or a.status.counts_as_applied]
    interviewed = [a for a in applied if a.interviews.all()]
    offered = [a for a in applied if a.offers.all()]
    first_interview_days = []
    for a in interviewed:
        if a.applied_date:
            first = min(timezone.localtime(i.scheduled_at).date() for i in a.interviews.all())
            first_interview_days.append(_days(a.applied_date, first))

    def pct(part, whole):
        return round(100 * part / whole) if whole else None

    channels = {}
    for a in applied:
        label = dict(Application.CHANNELS).get(a.applied_channel) or "Not recorded"
        row = channels.setdefault(label, {"label": label, "applied": 0, "interviews": 0, "offers": 0})
        row["applied"] += 1
        row["interviews"] += 1 if a.interviews.all() else 0
        row["offers"] += 1 if a.offers.all() else 0
    return {
        "tracked": len(apps),
        "applied": len(applied),
        "interviewed": len(interviewed),
        "offered": len(offered),
        "interview_rate": pct(len(interviewed), len(applied)),
        "offer_rate": pct(len(offered), len(applied)),
        "median_days_to_interview": int(median(first_interview_days)) if first_interview_days else None,
        "channels": sorted(channels.values(), key=lambda r: -r["applied"]),
        "referred_applied": sum(1 for a in applied if a.referrals.exists()),
        "referred_interviewed": sum(1 for a in interviewed if a.referrals.exists()),
    }
