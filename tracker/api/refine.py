"""The "Ask for changes" chat on a CV version and on a cover letter.

Same rules as the rest of the CV API: another person's version or letter is a 404, the AI is the person's own and optional, the answer is
fact-checked like a tailored one and saved as a new CV version (a cover letter keeps a revision list), and a flagged result stays locked
for download until the person approves it."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import CoverLetter, CVVersion, SiteConfig
from ..services import cvimprove, refine
from ..services.cvversions import CVError
from .common import throttle
from .cover import _detail as _letter_detail

router = Router()
AI_SETTINGS_LINK = "/profile/ai?preset=gemini"


class MessageIn(Schema):
    message: str


def _version(request, cv_id) -> CVVersion:
    return get_object_or_404(CVVersion.objects.select_related("application", "parent"), pk=cv_id, owner=request.user)


def _letter(request, cover_id) -> CoverLetter:
    return get_object_or_404(CoverLetter.objects.select_related("application"), pk=cover_id, owner=request.user)


def _ai(config) -> dict:
    return {"available": cvimprove.ai_ready(config), "settings_link": AI_SETTINGS_LINK, "missing_message": cvimprove.NO_KEY}


def _gate(request, config) -> None:
    if not cvimprove.ai_ready(config):
        raise HttpError(400, cvimprove.NO_KEY)  # before the throttle: a call that cannot happen should not use up the hour
    throttle(request, "refine", settings.STILLOPEN_REFINE_PER_HOUR)


@router.get("/cv/{cv_id}/refine", summary="The 'Ask for changes' conversation for a CV version")
def cv_state(request, cv_id: int):
    version = _version(request, cv_id)
    previous = refine.previous_cv(version)
    return {"ai": _ai(SiteConfig.for_user(request.user)), "messages": refine.cv_messages(version), "undo_to": previous.pk if previous else None}


@router.post("/cv/{cv_id}/refine", summary="Ask the person's AI to change a CV version; the answer is fact-checked and saved as a new version")
def cv_refine(request, cv_id: int, payload: MessageIn):
    version = _version(request, cv_id)
    config = SiteConfig.for_user(request.user)
    _gate(request, config)
    try:
        created, summary = refine.refine_cv(version, payload.message, config)
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {
        "id": created.pk, "summary": summary, "flagged": created.flagged, "flagged_count": len(created.check_report or []),
        "check_report": created.check_report or [], "exportable": created.exportable, "messages": refine.cv_messages(created), "undo_to": version.pk,
    }


@router.post("/cv/{cv_id}/refine/undo", summary="Go back to the version before an AI change (nothing is deleted)")
def cv_undo(request, cv_id: int):
    previous = refine.previous_cv(_version(request, cv_id))
    if previous is None:
        raise HttpError(400, "There is nothing to undo.")
    return {"id": previous.pk}


@router.get("/cover/{cover_id}/refine", summary="The 'Ask for changes' conversation for a cover letter")
def letter_state(request, cover_id: int):
    letter = _letter(request, cover_id)
    return {"ai": _ai(SiteConfig.for_user(request.user)), "messages": refine.letter_messages(letter), "can_undo": refine.can_undo_letter(letter)}


@router.post("/cover/{cover_id}/refine", summary="Ask the person's AI to change a cover letter; the answer is fact-checked and needs approval again")
def letter_refine(request, cover_id: int, payload: MessageIn):
    letter = _letter(request, cover_id)
    config = SiteConfig.for_user(request.user)
    _gate(request, config)
    try:
        summary = refine.refine_letter(letter, payload.message, config)
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"summary": summary, "letter": _letter_detail(letter), "messages": refine.letter_messages(letter), "can_undo": refine.can_undo_letter(letter)}


@router.post("/cover/{cover_id}/refine/undo", summary="Go back to the letter as it was before the last AI change")
def letter_undo(request, cover_id: int):
    letter = _letter(request, cover_id)
    try:
        summary = refine.undo_letter(letter, SiteConfig.for_user(request.user))
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"summary": summary, "letter": _letter_detail(letter), "messages": refine.letter_messages(letter), "can_undo": refine.can_undo_letter(letter)}
