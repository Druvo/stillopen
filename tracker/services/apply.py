"""The apply assistant. It never submits anything: it prepares, then records what the person did.

Recording ties an application to the exact CV version that was sent, the channel, the date, and a snapshot of the
job description (postings disappear), and schedules a follow-up reminder.
"""
from datetime import date, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone

from tracker.models import Application, CVVersion, Event, SiteConfig, Status
from tracker.services import cvversions

MAX_FOLLOW_UP_DAYS = 90
CHANNELS = {value for value, _ in Application.CHANNELS if value}


class ApplyError(Exception):
    pass


def sendable_versions(app: Application) -> list[CVVersion]:
    """CVs the person may record as sent: tailored versions for this job, then their current master.

    Versions with flagged, unapproved claims are never offered."""
    versions = [v for v in CVVersion.objects.filter(owner=app.owner, application=app).order_by("-created_at", "-id") if v.exportable]
    master = cvversions.latest_master(app.owner)
    if master:
        versions.append(master)
    return versions


def checklist(app: Application, config: SiteConfig, versions: list[CVVersion]) -> list[dict]:
    """Things worth knowing before applying. Each item: level 'ok' | 'warn' | 'info', and text."""
    items = []
    if app.live_state == "expired":
        items.append({"level": "warn", "text": "This posting looks closed. Check it before spending time on an application."})
    elif app.live_state == "active":
        items.append({"level": "ok", "text": "The posting was open the last time it was checked."})
    else:
        items.append({"level": "info", "text": "Not checked yet whether the posting is still open. Press “Are they still open?” on the dashboard."})
    days = app.days_left()
    if days is not None:
        if days < 0:
            items.append({"level": "warn", "text": f"The deadline passed {-days} day{'s' if days != -1 else ''} ago."})
        elif days <= config.urgent_days:
            items.append({"level": "warn", "text": f"The deadline is {'today' if days == 0 else f'in {days} day' + ('s' if days != 1 else '')}."})
        else:
            items.append({"level": "ok", "text": f"The deadline is in {days} days."})
    percent = app.match_percent(config.score_scale)
    if percent is None:
        items.append({"level": "info", "text": "No match score yet. Press Evaluate match on the dashboard."})
    elif percent < 50:
        items.append({"level": "warn", "text": f"Your match is {percent}%, which is a poor fit. A few well-chosen applications beat many weak ones."})
    else:
        items.append({"level": "ok", "text": f"Your match is {percent}%."})
    tailored = [v for v in versions if v.kind == "tailored"]
    if tailored:
        items.append({"level": "ok", "text": "You have a CV tailored for this job that passed the fact check or that you approved."})
    elif CVVersion.objects.filter(owner=app.owner, application=app).exists():
        items.append({"level": "warn", "text": "Your tailored CV for this job still has flagged claims. Review and approve it, or edit it, before sending."})
    else:
        items.append({"level": "info", "text": "No CV tailored for this job yet. You can tailor one now, or send your current CV."})
    if app.applied_cv_id:
        items.append({"level": "info", "text": "You already recorded an application for this job. Recording again updates the details."})
    return items


def applied_status() -> Status:
    status = Status.objects.filter(counts_as_applied=True, is_terminal=False).order_by("order").first()
    if status is None:
        raise ApplyError('No status counts as "applied". Add one under Statuses in the admin.')
    return status


def record(app: Application, version: CVVersion | None, channel: str, note: str, follow_up_days: int, config: SiteConfig,
           applied_on: date | None = None) -> Application:
    """Mark `app` as sent with `version`. Idempotent: running it again updates the details."""
    if version is not None:
        if version.owner_id != app.owner_id:
            raise ApplyError("That CV version is not yours.")
        if not version.exportable:
            raise ApplyError("That CV version has flagged claims. Edit it or approve it first.")
        if version.kind == "tailored" and version.application_id not in (None, app.pk):
            raise ApplyError("That CV was tailored for a different job.")
    if channel and channel not in CHANNELS:
        raise ApplyError("Unknown channel.")
    if not 1 <= follow_up_days <= MAX_FOLLOW_UP_DAYS:
        raise ApplyError(f"Follow-up must be between 1 and {MAX_FOLLOW_UP_DAYS} days.")
    today = timezone.localdate()
    applied_on = applied_on or today
    if applied_on > today:
        raise ApplyError("The application date cannot be in the future.")
    already = bool(app.applied_cv_id or (app.status.counts_as_applied and app.applied_date))
    if not app.status.counts_as_applied:  # never move someone backwards from Interview to Applied
        app.status = applied_status()
    app.applied_date = applied_on
    app.applied_cv = version
    app.applied_channel = channel
    app.applied_note = note.strip()[:300]
    app.follow_up_date = applied_on + timedelta(days=follow_up_days)
    app.jd_at_apply = app.description[:30000]
    app.save()
    channel_label = dict(Application.CHANNELS).get(channel, "")
    sent = f"CV v{version.pk}" if version else "no CV recorded"
    Event.objects.create(
        application=app, kind="applied",
        text=("Application details updated" if already else "Applied")
        + (f" via {channel_label}" if channel_label else "") + f" with {sent}. Follow up on {app.follow_up_date:%d %b %Y}.",
    )
    return app


def due_followups(owner, today: date | None = None):
    today = today or timezone.localdate()
    return (
        Application.objects.filter(owner=owner, follow_up_date__isnull=False, follow_up_date__lte=today, status__is_terminal=False)
        .select_related("status", "applied_cv")
        .order_by("follow_up_date")
    )


def due_followups_to_email(owner, today: date | None = None):
    """Due follow-ups this owner hasn't already been emailed about for their current follow_up_date -- a snooze
    or a new follow-up date naturally clears the "already emailed" marker, so it fires again when it falls due."""
    today = today or timezone.localdate()
    return due_followups(owner, today).exclude(follow_up_emailed_for=models.F("follow_up_date"))


def followup_digest_text(apps) -> str:
    today = timezone.localdate()
    lines = ["Follow-ups due on your StillOpen tracker:", ""]
    for app in apps:
        overdue = (today - app.follow_up_date).days
        when = "today" if overdue == 0 else f"{overdue} day{'s' if overdue != 1 else ''} overdue"
        lines.append(f"- {app.company} - {app.role} ({when}, applied {app.applied_date:%d %b %Y})" if app.applied_date else f"- {app.company} - {app.role} ({when})")
    lines += ["", "Open your dashboard to mark one done or push it back a few days."]
    return "\n".join(lines)


def send_followup_digest(owner, apps) -> bool:
    """One email per person per run, listing every follow-up that's newly due -- never one email per job.
    Returns False (and sends nothing) if the owner has no usable, verified address."""
    from allauth.account.models import EmailAddress

    apps = list(apps)
    if not apps:
        return False
    if not EmailAddress.objects.filter(user=owner, email=owner.email, verified=True).exists():
        return False
    count = len(apps)
    send_mail(
        subject=f"StillOpen: {count} follow-up{'s' if count != 1 else ''} due",
        message=followup_digest_text(apps),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[owner.email],
        fail_silently=False,
    )
    Application.objects.filter(pk__in=[a.pk for a in apps]).update(follow_up_emailed_for=models.F("follow_up_date"))
    return True


def followup_done(app: Application) -> None:
    app.follow_up_date = None
    app.save(update_fields=["follow_up_date"])
    Event.objects.create(application=app, kind="followup", text="Follow-up done")


def followup_snooze(app: Application, days: int) -> None:
    days = max(1, min(days, MAX_FOLLOW_UP_DAYS))
    app.follow_up_date = timezone.localdate() + timedelta(days=days)
    app.save(update_fields=["follow_up_date"])
    Event.objects.create(application=app, kind="followup", text=f"Follow-up postponed to {app.follow_up_date:%d %b %Y}")


def email_draft(app: Application) -> dict:
    """A plain starting point for an email application. Contains nothing the person has not said about themselves."""
    strengths = [i.text for i in app.insights.all() if i.kind == "strength"][:3]
    lines = [
        "Dear hiring team,",
        "",
        f"I would like to apply for the {app.role} position at {app.company}. My CV is attached.",
    ]
    if strengths:
        lines += ["", "Points from my evaluation of the role (check each one is accurate before sending):"] + [f"- {s}" for s in strengths]
    lines += ["", "I would welcome the chance to discuss the role.", "", "Kind regards,", "[Your name]"]
    return {"subject": f"Application: {app.role}", "body": "\n".join(lines)}
