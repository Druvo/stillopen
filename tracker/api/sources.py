"""A person's own company job boards for the new app. Same rules as `views_sources.py`: only a connector from the fixed list and a short name
are accepted (a pasted careers-page address is parsed for its name, never fetched), caps and the hourly limit apply, and the site-wide
boards are admin-only, so they are a 404 here."""
from urllib.parse import urlparse

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from .. import forms
from ..models import JobSource
from ..services import coverage, ownsources, sourcehealth
from ..services.throttle import throttled
from .account import read_payload
from .common import owned, validate_form

router = Router()


def _source(source: JobSource, health: dict | None = None) -> dict:
    return {
        "id": source.pk, "name": source.name, "connector": source.connector, "connector_label": source.get_connector_display(),
        "board_token": source.board_token, "enabled": source.enabled,
        "host": (urlparse(source.board_token).hostname or "") if source.connector == "careerpage" else "",
        "health": sourcehealth.public_health((health or {}).get(source.name)),
    }


def _page(user) -> dict:
    form = forms.OwnSourceForm()
    health = sourcehealth.health_by_name(user)
    shared = list(ownsources.shared_sources().order_by("name"))
    return {
        "mine": [_source(s, health) for s in JobSource.objects.filter(owner=user).order_by("name", "id")],
        "shared": [s.name for s in shared],
        # the shared boards, read-only: how each answered this person's own searches (a board no search has read yet is "unknown")
        "shared_health": [{"name": s.name, "health": sourcehealth.public_health(health.get(s.name))} for s in shared],
        "trouble": sourcehealth.last_search_trouble(user),
        "limit": settings.STILLOPEN_MAX_OWN_SOURCES,
        "connectors": [{"value": value, "label": label} for value, label in form.fields["connector"].choices if value != "careerpage"],  # a careers page has its own form
        "help": {name: str(field.help_text) for name, field in form.fields.items()},
    }


@router.get("/sources", summary="The person's own job boards, and how many are searched for everyone")
def list_sources(request):
    return _page(request.user)


@router.get("/sources/coverage", summary="Where jobs are found for each of the person's search areas, and what to do when a place is empty")
def sources_coverage(request):
    return coverage.for_user(request.user)


@router.post("/sources", summary="Check and add a company's job board")
def add_source(request):
    data, _ = read_payload(request)
    form = forms.OwnSourceForm(data)
    validate_form(form)
    cleaned = form.cleaned_data
    try:
        source, count = ownsources.add_own_source(
            request.user, cleaned["connector"], cleaned["board_token"], cleaned["name"],
            lambda: throttled(request.user, "source_add", settings.STILLOPEN_SOURCE_ADDS_PER_HOUR),
        )
    except ownsources.SourceRefused as refused:
        if refused.info:  # "already added" is not a problem: say so as plain information, like the classic page did
            return {"source": None, "openings": 0, "message": "", "info": str(refused)}
        raise HttpError(refused.status, str(refused)) from None
    message = f"Added {source.name}. It has {count} opening{'s' if count != 1 else ''} right now; your next search will include it."
    return {"source": _source(source), "openings": count, "message": message, "info": ""}


class CareerPageIn(Schema):
    url: str
    name: str = ""


@router.post("/sources/careers-page", summary="Check and add a company's own careers page (read like a search engine does: public JobPosting data, robots.txt obeyed)")
def add_careers_page(request, payload: CareerPageIn):
    form = forms.OwnSourceForm({"connector": "careerpage", "board_token": payload.url, "name": payload.name})
    validate_form(form)
    cleaned = form.cleaned_data
    try:
        source, count = ownsources.add_own_source(
            request.user, "careerpage", cleaned["board_token"], cleaned["name"],
            lambda: throttled(request.user, "source_add", settings.STILLOPEN_SOURCE_ADDS_PER_HOUR),
        )
    except ownsources.SourceRefused as refused:
        if refused.info:
            return {"source": None, "openings": 0, "message": "", "info": str(refused)}
        raise HttpError(refused.status, str(refused)) from None
    message = f"Added {source.name}. We found {count} opening{'s' if count != 1 else ''} on that page; your next search will include {'them' if count != 1 else 'it'}."
    return {"source": _source(source), "openings": count, "message": message, "info": ""}


@router.post("/sources/{source_id}/toggle", summary="Pause or resume one of the person's boards")
def toggle_source(request, source_id: int):
    source = owned(JobSource, request, source_id)
    source.enabled = not source.enabled
    source.save(update_fields=["enabled"])
    return {"source": _source(source)}


@router.delete("/sources/{source_id}", summary="Remove one of the person's boards")
def delete_source(request, source_id: int):
    owned(JobSource, request, source_id).delete()
    return {"ok": True}
