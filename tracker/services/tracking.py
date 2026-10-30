"""Putting jobs into a person's tracker: by hand, from a pasted link, or from a posting a search found.

The classic pages and the JSON API both call these, so the rules (the limit, the starting status, the details read from the posting) live once.
Everything is for one owner; nothing here looks at anyone else's rows."""
import re
import unicodedata

from django.conf import settings
from django.db import transaction
from django.db.models import ProtectedError, Q, RestrictedError
from django.utils import timezone

from tracker.models import Application, Event, KnowledgeSource, Posting, SiteConfig, Status
from tracker.services import geo, jobtext, knowledge


class TrackingError(Exception):
    """Plain words for the person (a limit reached, nothing to read)."""


class Duplicate(TrackingError):
    """The person already tracks this company and role; `job` is that job."""

    def __init__(self, job):
        self.job = job
        super().__init__(duplicate_message(job))


def starting_status() -> Status:
    return (
        Status.objects.filter(name="Saved").first()
        or Status.objects.filter(bucket__is_closed=False).order_by("order").first()
        or Status.objects.first()
    )


def job_limit_message() -> str:
    return f"You have reached the limit of {settings.STILLOPEN_MAX_APPLICATIONS} tracked jobs. Delete some first."


def at_job_limit(owner) -> bool:
    return Application.objects.filter(owner=owner).count() >= settings.STILLOPEN_MAX_APPLICATIONS


def add_job(owner, form) -> Application:
    """Save a valid `JobForm` as a new job of `owner`, then suggest its location, arrangement and so on from the posting."""
    app = form.save(commit=False)
    app.owner = owner
    app.status = starting_status()
    app.save()
    geo.fill_details(app)
    Event.objects.create(application=app, kind="note", text="Added")
    return app


# --- the same job twice ---------------------------------------------------------------------------------

_SENIORITY = {"senior", "sr", "junior", "jr", "lead", "principal"}
_COMPANY_SUFFIX = {"inc", "ltd", "llc", "limited", "corp", "corporation", "gmbh", "co", "company", "plc", "pte", "pvt", "bv", "sa", "ag"}


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9+#]+", plain)


def norm_key(company: str, role: str) -> str:
    """Company and role as one comparable text: case, punctuation, seniority words (Senior, Sr, Jr...) and company endings (Inc, Ltd...) ignored."""
    company_words = [w for w in _words(company) if w not in _COMPANY_SUFFIX] or _words(company)
    role_words = [w for w in _words(role) if w not in _SENIORITY] or _words(role)
    return f"{' '.join(company_words)}|{' '.join(role_words)}"


def duplicate_info(app: Application) -> dict:
    return {"id": app.pk, "company": app.company, "role": app.role, "status": app.status.name}


def duplicate_message(app: Application) -> str:
    return f"You already track {app.role} at {app.company} ({app.status.name})."


def find_duplicate(owner, company: str, role: str, url: str = "", exclude_id: int | None = None) -> Application | None:
    """The person's own job that is the same as this one: the same link, or the same company and role once case, punctuation and seniority words are ignored."""
    mine = Application.objects.filter(owner=owner).select_related("status")
    if exclude_id:
        mine = mine.exclude(pk=exclude_id)
    if url:
        same_link = mine.filter(url=url).first()
        if same_link:
            return same_link
    if not (company or "").strip() or not (role or "").strip():
        return None
    key = norm_key(company, role)
    for app in mine.order_by("id"):
        if norm_key(app.company, app.role) == key:
            return app
    return None


# --- taking a job off the tracker -------------------------------------------------------------------------

def _count_phrase(count: int, one: str, many: str) -> str:
    return f"its {one}" if count == 1 else f"{count} {many}"


def _preview(counts: dict, prep_plans: int, jobs: int = 1) -> dict:
    parts = []
    for key, one, many in (
        ("tailored_cvs", "tailored CV", "tailored CVs"), ("cover_letters", "cover letter", "cover letters"),
        ("interviews", "interview", "interviews"), ("referrals", "referral", "referrals"), ("offers", "offer", "offers"),
        ("files", "attached file", "attached files"),
    ):
        if counts.get(key):
            parts.append(_count_phrase(counts[key], one, many))
    if counts.get("prep_notes"):
        parts.append("its interview practice notes")
    if counts.get("history"):
        parts.append("its history")
    if parts:
        text = "This also removes " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]) + "."
    else:
        text = "Nothing else is attached to it."
    if jobs > 1:
        text = text.replace("its ", "their ").replace("This also removes", "This also removes").replace("Nothing else is attached to it.", "Nothing else is attached to them.")
    keeps = []
    if prep_plans:
        keeps.append("Your prep plan stays, but it will no longer be linked to the job.")
    keeps.append("A CV you already sent stays in your CV list, and the posting itself is not touched.")
    return {"counts": counts, "text": text, "keeps": " ".join(keeps)}


def removal_preview(app: Application) -> dict:
    """What removing one job takes with it, in numbers and in a sentence the confirm box shows word for word."""
    counts = {
        "tailored_cvs": app.cv_versions.count(),
        "cover_letters": app.cover_letters.count(),
        "interviews": app.interviews.count(),
        "referrals": app.referrals.count(),
        "offers": app.offers.count(),
        "files": app.documents.count(),
        "history": app.events.count(),
        "prep_notes": 1 if hasattr(app, "interview_prep") else 0,
    }
    return _preview(counts, app.prep_plans.count())


def bulk_removal_preview(ids: list[int]) -> dict:
    """The same, added up over several jobs (the caller has already checked every id is the person's own)."""
    from tracker.models import CoverLetter, CVVersion, Document, Interview, InterviewPrep, Offer, Referral
    from tracker.prep_models import PrepPlan

    ids = list(ids)
    counts = {
        "tailored_cvs": CVVersion.objects.filter(application_id__in=ids).count(),
        "cover_letters": CoverLetter.objects.filter(application_id__in=ids).count(),
        "interviews": Interview.objects.filter(application_id__in=ids).count(),
        "referrals": Referral.objects.filter(application_id__in=ids).count(),
        "offers": Offer.objects.filter(application_id__in=ids).count(),
        "files": Document.objects.filter(application_id__in=ids).count(),
        "history": Event.objects.filter(application_id__in=ids).count(),
        "prep_notes": InterviewPrep.objects.filter(application_id__in=ids).count(),
    }
    return _preview(counts, PrepPlan.objects.filter(application_id__in=ids).count(), jobs=len(ids))


def remove_jobs(owner, ids) -> int:
    """Delete these jobs of `owner` and everything that hangs off them (the caller has already checked every id is theirs). Returns how many went.

    Tailored CVs, cover letters, interviews, referrals, offers, files, fit notes, history and interview practice notes go with the job; a prep plan
    stays (unlinked), and so does the cost record of any AI check. Raises TrackingError if the database refuses (nothing is changed then)."""
    mine = Application.objects.filter(owner=owner, pk__in=list(ids))
    try:
        with transaction.atomic():
            count = mine.count()
            mine.delete()
    except (ProtectedError, RestrictedError):
        raise TrackingError("This job is still in use, so it could not be removed. Nothing was changed.")
    return count


def counted_in_stats() -> Q:
    """A job counts in the person's numbers unless it was archived without ever being applied to (an archived application still happened)."""
    return Q(archived_at__isnull=True) | Q(applied_date__isnull=False) | Q(status__counts_as_applied=True)


def archive_jobs(owner, ids) -> list[int]:
    """Archive these jobs of `owner` (the caller has already checked every id is theirs): they leave the dashboard and its counts but stay, with
    their status and everything else untouched. Returns the ids that changed (one already archived is left alone)."""
    now = timezone.now()
    fresh = list(Application.objects.filter(owner=owner, pk__in=list(ids), archived_at__isnull=True).values_list("pk", flat=True))
    if fresh:
        Application.objects.filter(pk__in=fresh).update(archived_at=now)
        Event.objects.bulk_create([Event(application_id=pk, kind="note", text="Archived") for pk in fresh])
    return fresh


def restore_jobs(owner, ids) -> list[int]:
    """Bring archived jobs of `owner` back to the dashboard exactly as they were. Returns the ids that changed."""
    archived = list(Application.objects.filter(owner=owner, pk__in=list(ids), archived_at__isnull=False).values_list("pk", flat=True))
    if archived:
        Application.objects.filter(pk__in=archived).update(archived_at=None)
        Event.objects.bulk_create([Event(application_id=pk, kind="note", text="Restored from the archive") for pk in archived])
    return archived


def add_posting(owner, posting: Posting, allow_duplicate: bool = False) -> tuple[Application, bool]:
    """Track a posting a search found. Returns (job, created); `created` is False when the person already tracks that link.
    Raises TrackingError at the limit, and `Duplicate` when the same company and role is already tracked under another link."""
    existing = Application.objects.filter(owner=owner, url=posting.url).first()
    if existing:
        return existing, False
    if at_job_limit(owner):
        raise TrackingError(job_limit_message())
    if not allow_duplicate:
        same = find_duplicate(owner, posting.company or posting.source.name, posting.title)
        if same:
            raise Duplicate(same)
    app = Application(
        owner=owner,
        company=posting.company or posting.source.name,
        role=posting.title,
        url=posting.url,
        location_text=posting.location,
        posting=posting,
        status=starting_status(),
        found_date=timezone.localdate(),
    )
    app.save()
    geo.fill_details(app)
    Event.objects.create(application=app, kind="note", text="Added from All postings")
    return app, True


def redetect(app: Application) -> list[str] | None:
    """Read the posting again. Returns the fields that changed, or None when the person set the details by hand (they are left alone)."""
    if app.details_source == "manual":
        return None
    return geo.fill_details(app, overwrite=True)


def fetch_prefill(url: str, config: SiteConfig) -> dict:
    """What the quick-add bar fills in from a link: {url, role, company, description}. Nothing is saved.

    Raises `jobtext.FetchError` (private addresses, unreadable pages) in plain words."""
    posting = jobtext.fetch_posting(url, config)
    role, company = jobtext.guess_role_company(posting["title"]) if posting["title"] else ("", "")
    return {"url": url, "role": role, "company": company, "description": posting["description"][:30000]}


def fit_check_posting(posting: Posting, owner, config: SiteConfig) -> dict:
    """"Check my fit" on a posting nobody has tracked yet: the same free, zero-token keyword match the dashboard
    uses once a job is tracked, run against the posting's own text. The full text is fetched on demand (same
    guarded path as the quick-add bar) since only a short `Posting.excerpt` is kept once a scan is done; the
    fetch is cached per posting for a day so repeat checks (or several people checking the same posting) don't
    re-fetch. Nothing is saved to the posting or the person's account.

    Raises `jobtext.FetchError` (private addresses, unreadable pages) or `ai.AIError` (no CV/notes yet) in plain words."""
    from django.core.cache import cache

    from tracker.services import ai, knowledge as knowledge_service

    key = f"postingfit:{posting.pk}"
    description = cache.get(key)
    if description is None:
        try:
            description = jobtext.fetch_posting(posting.url, config)["description"]
        except jobtext.FetchError:
            description = posting.excerpt
        cache.set(key, description, 24 * 3600)
    return ai.keyword_match(description, knowledge_service.all_candidate_text(config, owner))


def knowledge_limit_message() -> str:
    return f"You have reached the limit of {settings.STILLOPEN_MAX_KNOWLEDGE} documents."


def add_document(owner, form, config: SiteConfig) -> KnowledgeSource:
    """Save a valid `KnowledgeForm` for `owner`. Only the extracted text is kept, never the uploaded file."""
    source = form.save(commit=False)
    source.owner = owner
    source.file = ""
    source.save()
    knowledge.reindex_source(source, config)
    return source


def toggle_document(source: KnowledgeSource, config: SiteConfig) -> KnowledgeSource:
    source.enabled = not source.enabled
    source.save()
    knowledge.reindex_source(source, config)
    return source
