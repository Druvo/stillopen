"""The hiring process of a job as a timeline, "this came up" ticks, the person's question bank and company pages.

Everything is read from the person's own rows. Nothing here contacts anyone or changes a job's status: an outcome only *suggests*
the matching status (`suggest_for_outcome`), the person decides."""
import re
from urllib.parse import urlsplit

from django.utils import timezone

from tracker.models import Application, BankQuestion, CameUp, CompanyNote, Contact, Interview, Offer
from tracker.services import board

# How an outcome reads in a sentence, and the status the job could move to (offered, never applied).
OUTCOME_WORDS = {
    "pending": "scheduled", "done": "completed, waiting to hear", "passed": "passed", "rejected": "not moving on",
    "noshow": "did not happen (no-show)", "cancelled": "cancelled",
}
SUGGEST = {"passed": "Interview", "rejected": "Rejected"}

MAX_TAGS = 5
MAX_TAG_LEN = 30
MAX_BANK = 500


def suggest_for_outcome(item: Interview, outcome: str):
    name = SUGGEST.get(outcome)
    return board.suggest_for(item.application, name) if name else None


def summary_line(stages: list) -> str:
    """Plain words for where the process stands: "Round 2 of 4, passed". Cancelled stages are not counted as rounds."""
    live = [s for s in stages if s.outcome != "cancelled"]
    if not live:
        return "No stages yet. Add the first one when a company invites you to talk."
    total = len(live)
    # the latest stage that has moved past "scheduled", else the first one still to come
    decided = [i for i, s in enumerate(live) if s.outcome != "pending"]
    index = decided[-1] if decided else 0
    stage = live[index]
    return f"Round {index + 1} of {total}, {OUTCOME_WORDS.get(stage.outcome, stage.outcome)}"


def stage_row(item: Interview, now=None) -> dict:
    now = now or timezone.now()
    return {
        "id": item.pk, "kind": item.kind, "kind_label": item.get_kind_display(), "name": item.stage_name, "custom_label": item.custom_label,
        "scheduled_at": item.scheduled_at.isoformat(), "scheduled_local": timezone.localtime(item.scheduled_at).strftime("%Y-%m-%dT%H:%M"),
        "outcome": item.outcome, "outcome_label": item.get_outcome_display(), "outcome_word": OUTCOME_WORDS.get(item.outcome, item.outcome),
        "upcoming": item.outcome == "pending" and item.scheduled_at >= now, "where": item.where, "notes": item.notes,
        "interviewers": [{"id": c.pk, "name": c.name, "title": c.title} for c in item.contacts.all()],
    }


def timeline(app: Application) -> dict:
    """The stages of one job in date order, each with its interviewers, plus the offers and a one-line summary."""
    stages = list(app.interviews.prefetch_related("contacts").order_by("scheduled_at", "id"))
    now = timezone.now()
    return {
        "job": {"id": app.pk, "role": app.role, "company": app.company, "status": app.status.name},
        "summary": summary_line(stages),
        "stages": [stage_row(s, now) for s in stages],
        "offers": [{"id": o.pk, "status": o.status, "status_label": o.get_status_display()} for o in app.offers.all()],
    }


# --- "this came up" ---------------------------------------------------------------------------------

def set_came_up(owner, *, prep_question=None, application=None, key: str = "", value: bool) -> None:
    """Tick or untick one question. Exactly one of `prep_question` (a plan's quiz question) or `application` + `key` (a question in a
    job's interview prep) names it."""
    if prep_question is not None:
        lookup = {"owner": owner, "prep_question": prep_question}
    else:
        lookup = {"owner": owner, "application": application, "question_key": key[:64]}
    if value:
        CameUp.objects.get_or_create(**lookup)
    else:
        CameUp.objects.filter(**lookup).delete()


def tally_text(came_up: int, total: int) -> str:
    if total == 0:
        return ""
    if came_up == 0:
        return f"None of the {total} questions have come up yet. Tick one after an interview if it did."
    return f"{came_up} of {total} came up"


def plan_tally(owner, plan) -> dict:
    ids = list(plan.questions.filter(removed=False).values_list("pk", flat=True))
    ticked = list(CameUp.objects.filter(owner=owner, prep_question_id__in=ids).values_list("prep_question_id", flat=True))
    return {"total": len(ids), "came_up": len(ticked), "ticked": ticked, "text": tally_text(len(ticked), len(ids))}


def job_tally(owner, app, keys: list[str]) -> dict:
    ticked = [k for k in CameUp.objects.filter(owner=owner, application=app).values_list("question_key", flat=True) if k in keys]
    return {"total": len(keys), "came_up": len(ticked), "ticked": ticked, "text": tally_text(len(ticked), len(keys))}


# --- question bank ----------------------------------------------------------------------------------

def clean_tags(raw) -> list[str]:
    """Free-text tags: trimmed, lower-cased, no repeats, short, at most five. Anything that is not a list of text is refused."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Tags must be a short list of words.")
    out: list[str] = []
    for tag in raw:
        if not isinstance(tag, str):
            raise ValueError("Tags must be words.")
        tag = re.sub(r"\s+", " ", tag).strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LEN:
            raise ValueError(f"Each tag can be up to {MAX_TAG_LEN} characters.")
        if tag not in out:
            out.append(tag)
    if len(out) > MAX_TAGS:
        raise ValueError(f"Use at most {MAX_TAGS} tags.")
    return out


def bank_row(q: BankQuestion) -> dict:
    interviews = list(q.interviews.all())
    jobs = list(q.applications.all())
    return {
        "id": q.pk, "question": q.question, "answer": q.answer, "tags": q.tags,
        "interviews": [{"id": i.pk, "label": f"{i.stage_name} · {i.application.company}", "job_id": i.application_id} for i in interviews],
        "jobs": [{"id": a.pk, "label": f"{a.company} - {a.role}"} for a in jobs],
        "linked": bool(interviews or jobs),
        "updated_at": q.updated_at.isoformat(),
    }


def bank_list(owner, search: str = "", tag: str = "") -> list[BankQuestion]:
    rows = BankQuestion.objects.filter(owner=owner).prefetch_related("interviews__application", "applications")
    search = (search or "").strip().lower()
    tag = (tag or "").strip().lower()
    out = []
    for q in rows:
        if tag and tag not in q.tags:
            continue
        if search and search not in q.question.lower() and search not in q.answer.lower():
            continue
        out.append(q)
    return out


def all_tags(owner) -> list[str]:
    seen: set[str] = set()
    for tags in BankQuestion.objects.filter(owner=owner).values_list("tags", flat=True):
        seen.update(t for t in tags if isinstance(t, str))
    return sorted(seen)


# --- companies --------------------------------------------------------------------------------------

def company_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "")).strip().casefold()[:160]


def clean_link(value) -> str:
    """Text only, https only, never fetched. Blank is fine; anything else that is not a plain https address is refused."""
    value = ("" if value is None else str(value)).strip()
    if not value:
        return ""
    if len(value) > 300:
        raise ValueError("That link is too long.")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or re.search(r"[\s<>\"']", value):
        raise ValueError("Use a full web address that starts with https://")
    return value


def companies(owner) -> list[dict]:
    """One row per company name across the person's jobs and contacts (case-insensitive), watched ones first."""
    rows: dict[str, dict] = {}
    for company in Application.objects.filter(owner=owner).values_list("company", flat=True):
        key = company_key(company)
        if key:
            rows.setdefault(key, {"key": key, "name": company, "jobs": 0, "contacts": 0, "watched": False})["jobs"] += 1
    for company in Contact.objects.filter(owner=owner).exclude(company="").values_list("company", flat=True):
        key = company_key(company)
        if key:
            rows.setdefault(key, {"key": key, "name": company, "jobs": 0, "contacts": 0, "watched": False})["contacts"] += 1
    for n in CompanyNote.objects.filter(owner=owner):
        row = rows.get(n.key)
        if row:
            row["watched"] = n.watched
        elif n.watched or n.notes:
            rows[n.key] = {"key": n.key, "name": n.name, "jobs": 0, "contacts": 0, "watched": n.watched}
    return sorted(rows.values(), key=lambda r: (not r["watched"], r["name"].casefold()))


def company_page(owner, key: str) -> dict | None:
    key = company_key(key)
    if not key:
        return None
    apps = [a for a in Application.objects.filter(owner=owner).select_related("status") if company_key(a.company) == key]
    contacts = [c for c in Contact.objects.filter(owner=owner) if company_key(c.company) == key]
    note = CompanyNote.objects.filter(owner=owner, key=key).first()
    if not apps and not contacts and note is None:
        return None
    ids = [a.pk for a in apps]
    interviews = Interview.objects.filter(owner=owner, application_id__in=ids).select_related("application").prefetch_related("contacts")
    offers = Offer.objects.filter(owner=owner, application_id__in=ids).select_related("application")
    name = apps[0].company if apps else contacts[0].company if contacts else note.name
    return {
        "key": key, "name": name,
        "watched": bool(note and note.watched), "notes": note.notes if note else "",
        "website": note.website if note else "", "careers": note.careers if note else "", "linkedin": note.linkedin if note else "",
        "jobs": [{"id": a.pk, "role": a.role, "status": a.status.name, "applied_date": a.applied_date.isoformat() if a.applied_date else ""} for a in apps],
        "contacts": [{"id": c.pk, "name": c.name, "title": c.title} for c in contacts],
        "interviews": [
            {"id": i.pk, "job_id": i.application_id, "role": i.application.role, "name": i.stage_name, "when": timezone.localtime(i.scheduled_at).strftime("%Y-%m-%d %H:%M"),
             "outcome_label": i.get_outcome_display(), "interviewers": [c.name for c in i.contacts.all()]}
            for i in interviews
        ],
        "offers": [{"id": o.pk, "job_id": o.application_id, "role": o.application.role, "status_label": o.get_status_display(), "base": str(o.base), "currency": o.currency} for o in offers],
    }


def save_company(owner, key: str, name: str, data: dict) -> CompanyNote:
    note, _ = CompanyNote.objects.get_or_create(owner=owner, key=company_key(key), defaults={"name": name[:160]})
    for field in ("website", "careers", "linkedin"):
        if field in data:
            setattr(note, field, clean_link(data[field]))
    if "notes" in data:
        text = "" if data["notes"] is None else str(data["notes"])
        if len(text) > 4000:
            raise ValueError("Notes can be up to 4000 characters.")
        note.notes = text
    if "watched" in data:
        note.watched = bool(data["watched"])
    note.save()
    return note


def interviewed_you_for(contact: Contact) -> list[dict]:
    return [
        {"id": i.pk, "job_id": i.application_id, "label": f"{i.stage_name} · {i.application.company} - {i.application.role}",
         "when": timezone.localtime(i.scheduled_at).strftime("%Y-%m-%d")}
        for i in contact.interviews.select_related("application")
    ]
