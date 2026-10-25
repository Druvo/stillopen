"""Putting jobs into a person's tracker: by hand, from a pasted link, or from a posting a search found.

The classic pages and the JSON API both call these, so the rules (the limit, the starting status, the details read from the posting) live once.
Everything is for one owner; nothing here looks at anyone else's rows."""
from django.conf import settings
from django.utils import timezone

from tracker.models import Application, Event, KnowledgeSource, Posting, SiteConfig, Status
from tracker.services import geo, jobtext, knowledge


class TrackingError(Exception):
    """Plain words for the person (a limit reached, nothing to read)."""


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


def add_posting(owner, posting: Posting) -> tuple[Application, bool]:
    """Track a posting a search found. Returns (job, created); `created` is False when the person already tracks that link.
    Raises TrackingError at the limit."""
    existing = Application.objects.filter(owner=owner, url=posting.url).first()
    if existing:
        return existing, False
    if at_job_limit(owner):
        raise TrackingError(job_limit_message())
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
