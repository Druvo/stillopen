"""A person's own company job boards for the new app. Same rules as `views_sources.py`: only a connector from the fixed list and a short name
are accepted (a pasted careers-page address is parsed for its name, never fetched), caps and the hourly limit apply, and the site-wide
boards are admin-only, so they are a 404 here."""
from django.conf import settings
from ninja import Router
from ninja.errors import HttpError

from .. import forms
from ..models import JobSource
from ..services import ownsources
from ..services.throttle import throttled
from .account import read_payload
from .common import owned, validate_form

router = Router()


def _source(source: JobSource) -> dict:
    return {
        "id": source.pk, "name": source.name, "connector": source.connector, "connector_label": source.get_connector_display(),
        "board_token": source.board_token, "enabled": source.enabled,
    }


def _page(user) -> dict:
    form = forms.OwnSourceForm()
    return {
        "mine": [_source(s) for s in JobSource.objects.filter(owner=user).order_by("name", "id")],
        "shared": [s.name for s in ownsources.shared_sources().order_by("name")],
        "limit": settings.STILLOPEN_MAX_OWN_SOURCES,
        "connectors": [{"value": value, "label": label} for value, label in form.fields["connector"].choices],
        "help": {name: str(field.help_text) for name, field in form.fields.items()},
    }


@router.get("/sources", summary="The person's own job boards, and how many are searched for everyone")
def list_sources(request):
    return _page(request.user)


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
