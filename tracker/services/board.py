"""Moving a job between statuses. One rule, shared by the classic page, the JSON API and the board's drag-and-drop.

A move made here can be undone for a few minutes (`undo_status`): the event it writes remembers what the job looked like before, so
the applied date and follow-up date it set go away with it, and so does its line in the timeline."""
from datetime import date, timedelta

from django.utils import timezone

from ..models import Event, SiteConfig, Status
from . import tz

UNDO_MINUTES = 5

# Names that arrive from outside (the career-ops tracker, an assistant) and the status they mean now. Matched without regard to case.
STATUS_ALIASES = {"discarded": "Not for me", "skip": "Skipped"}

# What the screens call a status whose stored name code looks up (Saved, Evaluated and Applied are found by name, so they keep it).
STATUS_LABELS = {"Evaluated": "Checked"}


def canonical_name(name: str) -> str:
    """The current name for a status name that may be an old one."""
    name = (name or "").strip()
    return STATUS_ALIASES.get(name.lower(), name)


def find_status(name: str) -> Status | None:
    """The status called `name` (any case, old names too), or None."""
    return Status.objects.filter(name__iexact=canonical_name(name)).first()


def label_for(name: str) -> str:
    return STATUS_LABELS.get(name, name)


def _iso(value: date | None):
    return value.isoformat() if value else None


def change_status(app, status) -> bool:
    """Set `app.status`, stamp the applied date for statuses that count as applied and write the timeline event.

    Moving a job that was not yet applied to a status that counts as applied (and is not an ending, like Rejected) also sets the follow-up
    date the apply assistant would have set, when none is set, and says so in the timeline.

    Returns False when nothing changed (the job was already there)."""
    if app.status_id == status.pk:
        return False
    before = {
        "from": app.status_id, "to": status.pk, "applied_date": _iso(app.applied_date), "follow_up_date": _iso(app.follow_up_date),
    }
    was_applied = app.status.counts_as_applied
    app.status = status
    if status.counts_as_applied and not app.applied_date:
        app.applied_date = tz.today_for(app.owner_id)
    note = f"Status set to {status.name}"
    if status.counts_as_applied and not status.is_terminal and not was_applied and app.follow_up_date is None:
        days = (SiteConfig.for_user(app.owner) if app.owner_id else SiteConfig.load()).apply_followup_days
        app.follow_up_date = (app.applied_date or tz.today_for(app.owner_id)) + timedelta(days=days)
        note += f". Follow up on {app.follow_up_date:%d %b %Y}"
    app.save()
    Event.objects.create(application=app, kind="applied" if status.counts_as_applied else "status", text=note, undo=before)
    return True


def undo_status(app) -> bool:
    """Put the job back as it was before its latest status change, if that change was made in the last few minutes and the job has not moved since.

    Restores the status, the applied date and the follow-up date, and removes the timeline line. Returns False when there is nothing to undo."""
    event = app.events.filter(undo__isnull=False).order_by("-happened_at", "-id").first()
    if event is None or not isinstance(event.undo, dict):
        return False
    if timezone.now() - event.happened_at > timedelta(minutes=UNDO_MINUTES):
        return False
    before = event.undo
    previous = Status.objects.filter(pk=before.get("from")).first()
    if previous is None or app.status_id != before.get("to"):
        return False
    app.status = previous
    app.applied_date = date.fromisoformat(before["applied_date"]) if before.get("applied_date") else None
    app.follow_up_date = date.fromisoformat(before["follow_up_date"]) if before.get("follow_up_date") else None
    app.save()
    event.delete()
    return True


def suggest_for(app, target_name: str) -> dict | None:
    """The status to offer (never to apply) after an interview or offer was saved for `app`: `target_name` when the job is still before it.

    Statuses are compared in the order the admin set; a job that already ended (Rejected, Hired...) gets no suggestion."""
    app.refresh_from_db(fields=["status"])
    target = Status.objects.filter(name=target_name).first()
    current = app.status
    if target is None or current.pk == target.pk or current.is_terminal or current.order >= target.order:
        return None
    return {"id": target.pk, "name": target.name, "label": label_for(target.name)}
