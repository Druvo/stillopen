"""Adding and editing jobs, and the list of every posting a search has seen, for the new app.

Same rules as the classic pages: the forms are the classic forms (`JobForm`, `JobEditForm`), the limit and the starting status come from
`services/tracking.py`, a link pasted into the quick-add bar goes through the public-address guard, and a posting is only visible
through `JobSource.for_user`."""
import json

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from .. import forms
from ..models import Application, JobSource, Posting, SiteConfig
from ..services import fit as fit_service
from ..services import jobtext, scan, tracking
from .common import ApiFormError, owned_job, throttle, validate_form

router = Router()

PAGE_SIZE = 50

ADD_FIELDS = ["company", "role", "url", "deadline", "description", "notes"]
EDIT_FIELDS = [
    "company", "role", "url", "deadline", "location_text", "country", "arrangement", "sponsorship", "relocation", "employment_type",
    "seniority", "advertised_pay", "description", "notes",
]


def read_json(request) -> dict:
    """The JSON object the person sent; any keys, since the classic forms decide what is valid."""
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        raise HttpError(400, "Please check what you entered.")
    if not isinstance(body, dict):
        raise HttpError(400, "Please check what you entered.")
    return body


def _text(payload: dict, names: list[str]) -> dict:
    """The named fields of a JSON body as the strings a form expects (missing or null = empty)."""
    return {name: "" if payload.get(name) is None else str(payload[name]) for name in names}


def _options(form, names: list[str]) -> dict:
    return {name: [{"value": str(v), "label": str(label)} for v, label in form.fields[name].choices] for name in names}


@router.post("/quickadd", summary="Read the title and text of a job link, to fill the add-job form. Nothing is saved")
def quick_add(request):
    throttle(request, "quickadd", settings.STILLOPEN_QUICKADD_PER_HOUR)
    url = str(read_json(request).get("url") or "").strip()
    if not url:
        raise HttpError(400, "Paste a job URL first.")
    try:
        return {"ok": True, **tracking.fetch_prefill(url, SiteConfig.for_user(request.user))}
    except jobtext.FetchError as exc:
        raise HttpError(400, str(exc))


@router.post("/jobs", summary="Add a job to the tracker")
def add_job(request):
    if tracking.at_job_limit(request.user):
        raise ApiFormError({}, tracking.job_limit_message())
    form = forms.JobForm(_text(read_json(request), ADD_FIELDS))
    validate_form(form)
    app = tracking.add_job(request.user, form)
    return {"id": app.pk, "company": app.company, "role": app.role}


def _detail(app: Application) -> dict:
    form = forms.JobEditForm(instance=app)
    values = {name: form.initial.get(name, getattr(app, name, "")) for name in EDIT_FIELDS}
    values["deadline"] = app.deadline.isoformat() if app.deadline else ""
    return {
        "id": app.pk, "company": app.company, "role": app.role,
        "values": {k: ("" if v is None else str(v)) for k, v in values.items()},
        "details_source": app.details_source,
        "options": _options(form, ["arrangement", "sponsorship", "relocation", "employment_type", "seniority"]),
        "fit": fit_service.fit_flags(app),
    }


@router.get("/jobs/{job_id}/details", summary="Everything about a job the person may correct, and how well it fits what they want")
def get_details(request, job_id: int):
    return _detail(owned_job(request, job_id))


@router.put("/jobs/{job_id}/details", summary="Save corrections to a job")
def save_details(request, job_id: int):
    app = owned_job(request, job_id)
    form = forms.JobEditForm(_text(read_json(request), EDIT_FIELDS), instance=app)
    validate_form(form)
    form.save()
    app.refresh_from_db()
    return _detail(app)


@router.post("/jobs/{job_id}/redetect", summary="Read the posting again for location, arrangement and so on")
def redetect(request, job_id: int):
    app = owned_job(request, job_id)
    changed = tracking.redetect(app)
    if changed is None:
        raise HttpError(400, "You set these details yourself, so they are left alone. Clear a field and save to let detection fill it.")
    app.refresh_from_db()
    return {"ok": True, "changed": changed, **_detail(app)}


def _repost(posting: Posting):
    signal = scan.repost_signal(posting)
    return {"distinct_urls": signal["distinct_urls"], "distinct_dates": signal["distinct_dates"]} if signal else None


@router.get("/postings", summary="Every posting any search has seen, with whether the person already tracks it")
def list_postings(request, q: str = "", source: str = "", page: int = 1):
    sources = JobSource.for_user(request.user)
    qs = Posting.objects.filter(source__in=sources).select_related("source").order_by("-last_seen_at", "-id")
    q = q.strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(company__icontains=q))
    source = source.strip()
    if source:
        if not source.isdigit():
            raise HttpError(400, "Choose a source from the list.")
        qs = qs.filter(source_id=int(source))
    paged = Paginator(qs, PAGE_SIZE).get_page(page)
    tracked = dict(Application.objects.filter(owner=request.user).exclude(url="").values_list("url", "id"))
    return {
        "total": paged.paginator.count, "page": paged.number, "pages": paged.paginator.num_pages,
        "sources": [{"id": s.pk, "name": s.name, "connector": s.get_connector_display()} for s in sources.order_by("name")],
        "limit_message": tracking.job_limit_message() if tracking.at_job_limit(request.user) else "",
        "postings": [
            {
                "id": p.pk, "title": p.title, "company": p.company, "location": p.location, "url": p.url,
                "source": {"id": p.source_id, "name": p.source.name, "connector": p.source.get_connector_display()},
                "first_seen": p.first_seen_at.date().isoformat(), "last_seen": p.last_seen_at.date().isoformat(),
                "repost": _repost(p), "tracked": p.url in tracked, "job_id": tracked.get(p.url),
            }
            for p in paged
        ],
    }


@router.post("/postings/{posting_id}/add", summary="Add a posting a search found to the tracker")
def add_posting(request, posting_id: int):
    posting = get_object_or_404(Posting.objects.select_related("source"), pk=posting_id, source__in=JobSource.for_user(request.user))
    try:
        app, created = tracking.add_posting(request.user, posting)
    except tracking.TrackingError as exc:
        raise HttpError(400, str(exc))
    return {"id": app.pk, "created": created, "company": app.company, "role": app.role}
