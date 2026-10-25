"""Optional AI help for the new app: interview questions, practice feedback, application answers, a reading of a posting, role suggestions and
message drafts. Each one only suggests: nothing is saved as the person's words, sent or applied for. AI helpers need the person's own key
(a plain message says how to add one), are limited per person per hour, and another person's job is a 404."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import Contact, Interview, Offer, SiteConfig
from ..services import assist
from .common import owned, owned_job, throttle

router = Router()


def _config(request) -> SiteConfig:
    return SiteConfig.for_user(request.user)


def _limit(request, feature: str) -> None:
    throttle(request, f"assist:{feature}", settings.STILLOPEN_ASSIST_PER_HOUR)


def _run(call):
    try:
        return call()
    except assist.AssistError as exc:
        raise HttpError(400, str(exc))


@router.get("/assist/status", summary="Whether the person has an AI set up for the optional helpers")
def status(request):
    return {"ai": assist.has_ai(_config(request)), "settings_path": "/profile/ai?preset=gemini", "message": assist.NO_KEY_MESSAGE}


# --- 1. interview questions ----------------------------------------------------------------------------

@router.get("/jobs/{job_id}/interview-prep", summary="The latest interview questions made for a job, if any")
def get_interview_prep(request, job_id: int):
    app = owned_job(request, job_id)
    return {"prep": assist.stored_interview_prep(app), "ai": assist.has_ai(_config(request))}


@router.post("/jobs/{job_id}/interview-prep", summary="Write likely interview questions for a job, with outlines from the person's own material")
def make_interview_prep(request, job_id: int):
    app = owned_job(request, job_id)
    config = _config(request)
    _run(lambda: assist.require_ai(config))
    _limit(request, "interview_prep")
    return {"prep": _run(lambda: assist.interview_prep(app, config, request.user)), "ai": True}


class FeedbackIn(Schema):
    question: str
    answer: str


@router.post("/jobs/{job_id}/interview-prep/feedback", summary="Honest feedback on a written practice answer (not saved)")
def answer_feedback(request, job_id: int, payload: FeedbackIn):
    app = owned_job(request, job_id)
    config = _config(request)
    _run(lambda: assist.require_ai(config))
    _limit(request, "answer_feedback")
    return {"feedback": _run(lambda: assist.feedback(app, config, request.user, payload.question, payload.answer))}


# --- 3. application answers ------------------------------------------------------------------------------

class QuestionIn(Schema):
    question: str


@router.post("/jobs/{job_id}/application-answer", summary="A draft answer to an application-form question (checked against the person's own material, never sent)")
def application_answer(request, job_id: int, payload: QuestionIn):
    app = owned_job(request, job_id)
    config = _config(request)
    _run(lambda: assist.require_ai(config))
    _limit(request, "app_answer")
    return _run(lambda: assist.application_answer(app, config, request.user, payload.question))


# --- 4. posting summary and red flags -----------------------------------------------------------------------

@router.get("/jobs/{job_id}/summary", summary="The saved reading of a job's posting, if any")
def get_summary(request, job_id: int):
    app = owned_job(request, job_id)
    return {"summary": app.ai_summary or None, "ai": assist.has_ai(_config(request))}


@router.post("/jobs/{job_id}/summarise", summary="Read a posting: what it needs and plainly worded red flags (AI if set up, plain rules if not)")
def summarise(request, job_id: int):
    app = owned_job(request, job_id)
    config = _config(request)
    if assist.has_ai(config):
        _limit(request, "summarise")
    return {"summary": _run(lambda: assist.summarise(app, config, request.user)), "ai": assist.has_ai(config)}


# --- 5. roles and places from the CV ------------------------------------------------------------------------

class SuggestIn(Schema):
    cv: str | None = None


@router.post("/profile/suggest", summary="Roles (and places the CV states) to search for, from the person's CV")
def suggest(request, payload: SuggestIn):
    config = _config(request)
    if assist.has_ai(config):
        _limit(request, "suggest_roles")
    return _run(lambda: assist.suggest_roles(config, request.user, payload.cv))


# --- 6. follow-up and thank-you drafts -----------------------------------------------------------------------

class MessageIn(Schema):
    kind: str
    note: str = ""
    interview_id: int | None = None
    polish: bool = False


@router.post("/jobs/{job_id}/message-draft", summary="A short email draft (a free template, or polished by AI). It is never sent")
def message_draft(request, job_id: int, payload: MessageIn):
    app = owned_job(request, job_id)
    config = _config(request)
    interview = get_object_or_404(Interview, pk=payload.interview_id, owner=request.user, application=app) if payload.interview_id else None
    if payload.polish:
        _run(lambda: assist.require_ai(config))
        _limit(request, "message_draft")
    return _run(lambda: assist.message_draft(app, config, request.user, payload.kind, payload.note, interview, payload.polish))


# --- 7. fill the Add job form from pasted text -----------------------------------------------------------------------

class PasteIn(Schema):
    text: str


@router.post("/jobs/parse-text", summary="Read pasted posting text into company, role, place, pay, deadline and link (plain rules, refined by AI if set up). Nothing is saved")
def parse_text(request, payload: PasteIn):
    config = _config(request)
    if assist.has_ai(config) and not all(assist.rule_parse_posting(payload.text).values()):  # the AI is only asked when the rules left gaps
        _limit(request, "parse_text")
    return _run(lambda: assist.parse_posting(config, request.user, payload.text))


# --- 8. offers in words -----------------------------------------------------------------------------------------------

class CompareIn(Schema):
    offer_ids: list[int]
    counter_offer_id: int | None = None  # which offer the counter note is about (default: the first listed)


@router.post("/offers/compare-note", summary="Plain-words differences between 2 to 4 of the person's own offers (per currency, never converted), what to ask, and with AI a counter-offer note")
def compare_offers(request, payload: CompareIn):
    ids = list(dict.fromkeys(payload.offer_ids))
    offers = [owned(Offer, request, pk, application__owner=request.user) for pk in ids]  # someone else's id is a 404
    if not 2 <= len(offers) <= 4:
        raise HttpError(400, "Choose two to four offers to compare.")
    focus = next((o for o in offers if o.pk == payload.counter_offer_id), None) if payload.counter_offer_id else None
    if payload.counter_offer_id and focus is None:
        raise HttpError(404, "Not found.")
    config = _config(request)
    if assist.has_ai(config):
        _limit(request, "offer_note")
    return _run(lambda: assist.offer_note(config, request.user, offers, focus))


# --- 9. a referral request to a contact -------------------------------------------------------------------------------

class ReferralIn(Schema):
    job_id: int
    polish: bool = False


@router.post("/contacts/{contact_id}/referral-draft", summary="A short referral-request message to a contact (a free template, or polished by AI). It is never sent")
def referral_draft(request, contact_id: int, payload: ReferralIn):
    contact = owned(Contact, request, contact_id)
    app = owned_job(request, payload.job_id)
    config = _config(request)
    if payload.polish:
        _run(lambda: assist.require_ai(config))
        _limit(request, "referral_draft")
    return _run(lambda: assist.referral_draft(contact, app, config, request.user, payload.polish))
