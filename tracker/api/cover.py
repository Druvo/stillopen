"""Cover letters for the new app. Same rules as `views_cover.py`: every save re-checks the letter and withdraws an earlier approval, a flagged
letter stays locked for download until approved, nothing is ever sent for the person, and another person's letter is a 404."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import CoverLetter, SiteConfig
from ..services import coverletter
from ..services.cvversions import CVError
from ..services.throttle import throttled
from .common import owned_job

router = Router()


def _letter(request, cover_id) -> CoverLetter:
    return get_object_or_404(CoverLetter.objects.select_related("application"), pk=cover_id, owner=request.user)


def _detail(letter: CoverLetter) -> dict:
    app = letter.application
    downloads = None
    if letter.exportable:
        downloads = {"docx": reverse("cover_download", args=[letter.pk, "docx"]), "txt": reverse("cover_download", args=[letter.pk, "txt"])}
    return {
        "id": letter.pk, "content": letter.content, "source": letter.source, "source_label": letter.get_source_display(), "provider": letter.provider,
        "updated_at": letter.updated_at.isoformat(), "job": {"id": app.pk, "role": app.role, "company": app.company},
        "flagged": letter.flagged, "flagged_count": len(letter.check_report or []), "check_report": letter.check_report or [],
        "approved": letter.approved, "approved_at": letter.approved_at.isoformat() if letter.approved_at else None,
        "exportable": letter.exportable, "downloads": downloads,
    }


@router.get("/cover/{cover_id}", summary="One cover letter with its fact-check results")
def get_letter(request, cover_id: int):
    return _detail(_letter(request, cover_id))


class SaveIn(Schema):
    content: str


@router.post("/cover/{cover_id}/save", summary="Save the letter's text (it is checked again)")
def save_letter(request, cover_id: int, payload: SaveIn):
    letter = _letter(request, cover_id)
    try:
        coverletter.update(letter, payload.content, SiteConfig.for_user(request.user))
    except CVError as exc:
        raise HttpError(400, str(exc))
    return _detail(letter)


@router.post("/cover/{cover_id}/approve", summary="Say the flagged items are true, which unlocks downloads")
def approve_letter(request, cover_id: int):
    letter = _letter(request, cover_id)
    coverletter.approve(letter)
    return {"ok": True, "exportable": letter.exportable}


@router.delete("/cover/{cover_id}", summary="Delete a cover letter")
def delete_letter(request, cover_id: int):
    letter = _letter(request, cover_id)
    letter.delete()
    return {"ok": True}


class WriteIn(Schema):
    mode: str = "auto"


@router.post("/jobs/{job_id}/cover-letter", summary="Write a cover letter for a job")
def write_letter(request, job_id: int, payload: WriteIn):
    app = owned_job(request, job_id)
    if throttled(request.user, "cvgen", settings.STILLOPEN_CVGEN_PER_HOUR):
        raise HttpError(429, "Too many requests this hour. Try again later.")  # the classic page's own words
    mode = payload.mode if payload.mode in ("auto", "ai", "keywords") else "auto"
    try:
        letter = coverletter.generate(app, SiteConfig.for_user(request.user), mode)
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"id": letter.pk, "flagged": letter.flagged, "flagged_count": len(letter.check_report or [])}
