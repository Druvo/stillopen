"""The "How you match" card of a job, and "Add to my profile" for a requirement the person's material does not show.

Opening the card reads the posting with no AI and compares it with the person's own CV and notes (`services/matchcard.py`); their own AI can read the
posting instead, only when they press the button. A fact is only ever added from words the person typed. Every job and note is the person's own."""
from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import SiteConfig
from ..services import assist, matchcard, strength
from .common import owned_job, throttle

router = Router()


@router.get("/jobs/{job_id}/match-card", summary="What the posting asks for and which of it the person's own material covers, with where")
def get_card(request, job_id: int):
    app = owned_job(request, job_id)
    return matchcard.card(app, SiteConfig.for_user(request.user), request.user)


@router.post("/jobs/{job_id}/match-card/ai", summary="Read the posting's requirements with the person's own AI (only when they ask)")
def read_with_ai(request, job_id: int):
    app = owned_job(request, job_id)
    config = SiteConfig.for_user(request.user)
    try:
        assist.require_ai(config)
    except assist.AssistError as exc:
        raise HttpError(400, str(exc))
    throttle(request, "assist:match_card", settings.STILLOPEN_ASSIST_PER_HOUR)
    try:
        matchcard.read_with_ai(app, config, request.user)
    except assist.AssistError as exc:
        raise HttpError(400, str(exc))
    return matchcard.card(app, config, request.user)


class FactIn(Schema):
    text: str


@router.post("/jobs/{job_id}/match-card/fact", summary="Add a fact the person typed to their own notes")
def add_fact(request, job_id: int, payload: FactIn):
    app = owned_job(request, job_id)
    config = SiteConfig.for_user(request.user)
    try:
        result = matchcard.add_fact(request.user, config, payload.text, app)
    except matchcard.FactError as exc:
        raise HttpError(400, str(exc))
    return {**result, "card": matchcard.card(app, config, request.user)}


@router.get("/profile/strength", summary="How much of what matching needs is filled in, and the three most useful things still missing")
def profile_strength(request):
    return strength.meter(request.user)
