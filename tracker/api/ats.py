"""The CV quality features: the free ATS check, optional "Improve with AI", and the guided builder for a person with no CV yet.

Same rules as the rest of the CV API: another person's CV or job is a 404, the AI is optional and uses only the person's own key, and nothing
is applied for them (suggestions are text; the screen edits the editor and the person saves a new version)."""
from django.conf import settings
from django.core.cache import cache
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import Application, CVVersion, SiteConfig
from ..services import ats, cvbuilder, cvimprove
from ..services.cvversions import CVError, source_texts
from .common import owned, owned_job, throttle

router = Router()
AI_SETTINGS_LINK = "/profile/ai?preset=gemini"


@router.get("/cv/job-choices", summary="The person's jobs (for checking a CV against one) and whether their AI is set up")
def job_choices(request):
    config = SiteConfig.for_user(request.user)
    ai_info = {"available": cvimprove.ai_ready(config), "settings_link": AI_SETTINGS_LINK, "missing_message": cvimprove.NO_KEY}
    jobs = Application.objects.filter(owner=request.user).order_by("-id").values("id", "role", "company", "description")[:200]
    return {"ai": ai_info, "jobs": [{"id": j["id"], "role": j["role"], "company": j["company"], "has_description": bool((j["description"] or "").strip())} for j in jobs]}


@router.get("/cv/{cv_id}/ats", summary="Check a CV the way an applicant tracking system reads it (free, no AI); add ?job= to compare with a job")
def check_cv(request, cv_id: int, job: int | None = None):
    version = owned(CVVersion, request, cv_id)
    throttle(request, "ats", settings.STILLOPEN_ATS_PER_HOUR)
    config = SiteConfig.for_user(request.user)
    result = ats.check_text(version.content)
    result["version"] = {"id": version.pk, "label": version.label}
    result["ai"] = {"available": cvimprove.ai_ready(config), "settings_link": AI_SETTINGS_LINK, "missing_message": cvimprove.NO_KEY}
    result["job"] = None
    result["coverage"] = None
    if job is not None:
        app = owned_job(request, job)
        if not (app.description or "").strip():
            raise HttpError(400, "This job has no description yet. Paste the posting text into the job, then check again.")
        coverage = ats.coverage(version.content, app.description, source_texts(request.user, config), cache.get("scan-common-terms") or frozenset())
        if coverage is None:
            raise HttpError(400, "We could not find enough words in this job's description to compare. Paste more of the posting into the job.")
        result["job"] = {"id": app.pk, "role": app.role, "company": app.company}
        result["coverage"] = coverage
    return result


class ImproveIn(Schema):
    job_id: int | None = None


@router.post("/cv/{cv_id}/improve", summary="Ask the person's own AI for up to six text suggestions (nothing is changed)")
def improve_cv(request, cv_id: int, payload: ImproveIn):
    version = owned(CVVersion, request, cv_id)
    config = SiteConfig.for_user(request.user)
    app = owned_job(request, payload.job_id) if payload.job_id is not None else None
    if not cvimprove.ai_ready(config):
        raise HttpError(400, cvimprove.NO_KEY)  # before the throttle: a call that cannot happen should not use up the hour
    throttle(request, "cvimprove", settings.STILLOPEN_CVIMPROVE_PER_HOUR)
    try:
        return cvimprove.improve(request.user, config, version.content, app.description if app else "")
    except CVError as exc:
        raise HttpError(400, str(exc))


class BuilderIn(Schema):
    answers: dict
    polish: bool = False


@router.post("/cv/builder", summary="Build a CV from the wizard's answers and save it as the person's newest CV version")
def build_cv(request, payload: BuilderIn):
    config = SiteConfig.for_user(request.user)
    if payload.polish and not cvimprove.ai_ready(config):
        raise HttpError(400, cvimprove.NO_KEY)
    throttle(request, "cvbuilder", settings.STILLOPEN_CVBUILDER_PER_HOUR)
    if payload.polish:
        throttle(request, "cvimprove", settings.STILLOPEN_CVIMPROVE_PER_HOUR)
    try:
        return cvbuilder.build_and_save(request.user, config, payload.answers, payload.polish)
    except CVError as exc:
        raise HttpError(400, str(exc))
