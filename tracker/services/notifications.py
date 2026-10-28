"""The in-app notification centre (the bell in the header). Short notices for things that already happened; nothing here changes a job.

Producers call `notify(...)` from code that already knows the event happened. A notice never carries job text or anything a person
typed beyond a company and role; `link` is an app path only. A person can switch each kind off (`UserProfile.notify_muted`), and at most
NOTIFICATION_CAP are kept per person."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from tracker.models import Notification, UserProfile

NOTIFICATION_CAP = 200
TEXT_MAX = 300

KINDS = {
    "search": "A search finished with new jobs",
    "deadline": "A deadline is close",
    "closed": "A job turned out to be closed",
    "followup": "A follow-up is due",
    "interview": "An interview reminder was sent",
    "drafts": "CV drafts are waiting for you",
}


def muted_kinds(user) -> set[str]:
    return {k for k in (UserProfile.for_user(user).notify_muted or []) if k in KINDS}


def set_muted(user, kinds) -> list[str]:
    """Replace the person's switched-off kinds; unknown names are ignored."""
    muted = sorted({k for k in kinds if k in KINDS})
    profile = UserProfile.for_user(user)
    profile.notify_muted = muted
    profile.save(update_fields=["notify_muted"])
    return muted


def _safe_link(link: str) -> str:
    """An app path ("/jobs/3") or nothing: never an address on another site."""
    link = (link or "").strip()
    return link[:200] if link.startswith("/") and not link.startswith("//") and "\\" not in link else ""


def notify(owner, kind: str, title: str, text: str = "", link: str = "", key: str = "", muted: set[str] | None = None) -> Notification | None:
    """Make one notice. Returns None when that kind is switched off or this `key` was already announced. Never raises: a notice
    must not break the search, check or email that produced it."""
    if kind not in KINDS or owner is None:
        return None
    try:
        if kind in (muted_kinds(owner) if muted is None else muted):
            return None
        key = key[:80]
        if key and Notification.objects.filter(owner=owner, dedupe_key=key).exists():
            return None
        with transaction.atomic():
            made = Notification.objects.create(owner=owner, kind=kind, title=title.strip()[:120], text=text.strip()[:TEXT_MAX], link=_safe_link(link), dedupe_key=key)
        _trim(owner)
        return made
    except IntegrityError:
        return None  # the same key raced in from another thread
    except Exception:  # noqa: BLE001 - bookkeeping only
        return None


def _trim(owner) -> None:
    extra = Notification.objects.filter(owner=owner).order_by("-created_at", "-pk").values_list("pk", flat=True)[NOTIFICATION_CAP:]
    ids = list(extra)
    if ids:
        Notification.objects.filter(owner=owner, pk__in=ids).delete()


def visible(user):
    return Notification.objects.filter(owner=user, cleared=False)


def unread_count(user) -> int:
    return visible(user).filter(read_at__isnull=True).count()


def serialise(n: Notification) -> dict:
    return {
        "id": n.pk, "kind": n.kind, "title": n.title, "text": n.text, "link": n.link,
        "created_at": n.created_at.isoformat(), "read": n.read_at is not None,
    }


def listing(user, limit: int = 100) -> dict:
    items = list(visible(user)[: max(1, min(limit, NOTIFICATION_CAP))])
    return {"items": [serialise(n) for n in items], "unread": unread_count(user)}


def summary(user) -> dict:
    return {"unread": unread_count(user)}


def mark_read(user, pk: int) -> bool:
    return bool(visible(user).filter(pk=pk, read_at__isnull=True).update(read_at=timezone.now())) or visible(user).filter(pk=pk).exists()


def mark_all_read(user) -> int:
    return visible(user).filter(read_at__isnull=True).update(read_at=timezone.now())


def clear_one(user, pk: int) -> bool:
    return bool(visible(user).filter(pk=pk).update(cleared=True, read_at=timezone.now()))


def clear_all(user) -> int:
    return visible(user).update(cleared=True, read_at=timezone.now())


# --- producers -----------------------------------------------------------------------------------------------------------

def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def search_finished(run) -> None:
    """A search that added jobs (a search that found nothing new is not worth a notice)."""
    added = run.added or 0
    if added < 1 or run.owner_id is None:
        return
    notify(run.owner, "search", f"Your search found {_plural(added, 'new job')}", "Open your dashboard to see them, best match first.", "/", key=f"search:{run.pk}")


def job_closed(app) -> None:
    if app.owner_id is None:
        return
    notify(app.owner, "closed", f"{app.company}: the posting looks closed", f"{app.role}. Check the page before you spend time on it.", f"/jobs/{app.pk}/edit", key=f"closed:{app.pk}")


def interview_reminders_sent(owner, items) -> None:
    for i in items:
        when = timezone.localtime(i.scheduled_at)
        notify(owner, "interview", f"Interview soon: {i.application.company}", f"{i.get_kind_display()} on {when:%a %d %b} at {when:%H:%M}.", "/interviews", key=f"interview:{i.pk}")


def drafts_waiting(owner, made: int) -> None:
    if made < 1:
        return
    notify(owner, "drafts", f"{_plural(made, 'CV draft')} waiting for your review", "Nothing is used until you approve it.", "/", key=f"drafts:{timezone.now():%Y%m%d%H%M}:{made}")


def sync_dashboard(user, cards, followups) -> None:
    """Deadlines inside the urgent window and follow-ups that are due, from the lists the dashboard has already worked out (no extra
    reads except one for the keys that already exist). Safe to run on every dashboard load: each key is announced once."""
    wanted = []
    for c in cards:
        app = c["app"]
        if c.get("urgent") and app.deadline and not c.get("overdue") and not app.status.counts_as_applied:
            days = c.get("days_left")
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days" if days is not None else "soon"
            wanted.append(("deadline", f"deadline:{app.pk}:{app.deadline.isoformat()}", f"{app.company}: apply by {when}", app.role, f"/jobs/{app.pk}/apply"))
    for a in followups:
        wanted.append(("followup", f"followup:{a['id']}:{a['follow_up_date']}", f"Follow up with {a['company']}", f"{a['role']}. The date you set has come.", f"/jobs/{a['id']}/apply"))
    if not wanted:
        return
    keys = [w[1] for w in wanted]
    known = set(Notification.objects.filter(owner=user, dedupe_key__in=keys).values_list("dedupe_key", flat=True))
    muted = muted_kinds(user)
    for kind, key, title, text, link in wanted[:20]:
        if key not in known:
            notify(user, kind, title, text, link, key=key, muted=muted)
