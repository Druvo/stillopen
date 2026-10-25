from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import django_auth

from ..models import Application, Bucket, JobSource, ScoreBand, SiteConfig, Status, UserProfile
from ..services import ai, board, geo, guide, liveness, quiz, scan
from ..services import apply as apply_service
from ..views import card_for, throttled

api = NinjaAPI(
    title="StillOpen",
    version="1",
    urls_namespace="api",
    auth=django_auth,  # session cookie plus CSRF on every unsafe method; unauthenticated -> 401
    docs_url=None,
)


@api.exception_handler(HttpError)
def _plain_errors(request, exc):
    return api.create_response(request, {"error": str(exc)}, status=exc.status_code)


def owned(request, pk) -> Application:
    """The person's own job or a 404, the same as the classic pages."""
    return get_object_or_404(Application, pk=pk, owner=request.user)


def too_many():
    return HttpError(429, "Too many requests. Try again later.")


class StatusIn(Schema):
    status: int


# --- who am I ------------------------------------------------------------------------------------

@api.get("/me", summary="The signed-in person")
def me(request):
    user = request.user
    return {
        "id": user.pk,
        "name": guide.first_name(user),
        "email": user.email,
        "is_staff": user.is_staff,
        "greeting": guide.greeting(user, timezone.localtime()),
    }


# --- dashboard -----------------------------------------------------------------------------------

def _job(card) -> dict:
    app = card["app"]
    return {
        "id": app.pk,
        "company": app.company,
        "role": app.role,
        "url": app.url,
        "status_id": app.status_id,
        "bucket_key": card["bucket_key"],
        "percent": card["percent"],
        "band": {"label": card["band"].label, "color": card["band"].color} if card["band"] else None,
        "decision": app.decision,
        "summary": app.summary,
        "location": app.location_text,
        "country": app.country,
        "country_name": geo.country_name(app.country) if app.country else "",
        "arrangement": app.arrangement,
        "found_date": app.found_date.isoformat(),
        "applied_date": app.applied_date.isoformat() if app.applied_date else None,
        "deadline": app.deadline.isoformat() if app.deadline else None,
        "days_left": card["days_left"],
        "urgent": card["urgent"],
        "overdue": card["overdue"],
        "live_state": app.live_state,
        "live_detail": app.live_detail,
        "strengths": [i.text for i in card["strengths"]],
        "gaps": [i.text for i in card["gaps"]],
        "fit_level": card["fit_level"],
        "fit_text": card["fit_text"],
        "has_cv": card["cv"] is not None,
        "repost": bool(card["repost"]),
        "skill_matched": card["skill_matched"],
        "evaluated": app.ai_evaluated_at is not None or app.score is not None,
        "edit_url": reverse("job_edit", args=[app.pk]),
        "apply_url": reverse("apply_page", args=[app.pk]),
        "tailor_url": reverse("tailor_cv", args=[app.pk]),
        "cover_url": reverse("write_cover_letter", args=[app.pk]),
        "prep_url": reverse("prep_create", args=[app.pk]),
    }


@api.get("/dashboard", summary="Every job of the signed-in person, with the columns it can sit in")
def dashboard(request):
    user = request.user
    config = SiteConfig.for_user(user)
    profile = UserProfile.for_user(user)
    bands = list(ScoreBand.objects.all())
    buckets = list(Bucket.objects.all())
    statuses = list(Status.objects.select_related("bucket"))
    areas = list(user.search_areas.all())
    scan.maybe_auto_start(user)
    apps = (
        Application.objects.filter(owner=user)
        .select_related("status", "status__bucket", "source", "posting", "posting__source", "applied_cv")
        .prefetch_related("insights", "documents__kind", "cv_versions", "events")
    )
    cards = []
    for app in apps:
        card = card_for(app, config, bands, areas, profile)
        card["bucket_key"] = app.effective_bucket(config).key
        cards.append(card)
    cards.sort(key=lambda c: (0 if c["urgent"] else 1, -(c["percent"] if c["percent"] is not None else -1)))
    scored = [c["percent"] for c in cards if c["percent"] is not None]
    submitted = [c for c in cards if c["app"].status.counts_as_applied]
    scan_run = scan.current_run(user)
    next_step = guide.next_step(
        profile, cards, has_areas=bool(areas),
        searching=bool(scan_run and scan_run.running),
        prep_due=quiz.due_plans(user) if config.prep_enabled else None,
    )
    return {
        "greeting": guide.greeting(user, timezone.localtime()),
        "buckets": [{"key": b.key, "label": b.label, "description": b.description, "is_closed": b.is_closed} for b in buckets],
        "statuses": [
            {"id": s.pk, "name": s.name, "bucket_key": s.bucket.key, "color": s.color, "counts_as_applied": s.counts_as_applied}
            for s in statuses
        ],
        "jobs": [_job(c) for c in cards],
        "stats": {
            "total": len(cards),
            "submitted": len(submitted),
            "average_match": round(sum(scored) / len(scored)) if scored else None,
            "urgent": sum(1 for c in cards if c["urgent"]),
        },
        "followups": [
            {"id": a.pk, "company": a.company, "role": a.role, "follow_up_date": a.follow_up_date.isoformat()}
            for a in apply_service.due_followups(user)
        ],
        "next_step": next_step,
        "can_scan": JobSource.for_user(user, enabled=True).exists(),
    }


# --- actions on one job --------------------------------------------------------------------------

@api.patch("/jobs/{job_id}/status", summary="Move a job to another status")
def set_job_status(request, job_id: int, payload: StatusIn):
    app = owned(request, job_id)
    status = get_object_or_404(Status.objects.select_related("bucket"), pk=payload.status)
    board.change_status(app, status)
    return {"ok": True, "status_id": status.pk, "status": status.name, "bucket_key": status.bucket.key}


@api.post("/jobs/{job_id}/evaluate", summary="Check how well a job fits")
def evaluate_job(request, job_id: int):
    app = owned(request, job_id)
    if throttled(request.user, "evaluate", settings.STILLOPEN_EVALS_PER_HOUR):
        raise too_many()
    try:
        result = ai.evaluate_application(app, SiteConfig.for_user(request.user))
    except ai.AIError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True, "match_percent": result["match_percent"], "method": app.ai_method}


# --- search and open/closed progress -------------------------------------------------------------

def _progress(run, extra=False) -> dict:
    if run is None:
        out = {"running": False, "done": 0, "total": 0, "error": ""}
        if extra:
            out.update({"found": 0, "added": 0})
        return out
    out = {"running": run.running, "done": run.done, "total": run.total, "error": run.error}
    if extra:
        out.update({"found": run.found, "added": run.added})
    return out


@api.post("/scan", summary="Search for new jobs")
def scan_start(request):
    if throttled(request.user, "scan", settings.STILLOPEN_SCANS_PER_HOUR):
        raise too_many()
    return _progress(scan.start_run(request.user), extra=True)


@api.get("/scan/status", summary="Progress of the person's latest search")
def scan_status(request):
    return _progress(scan.current_run(request.user), extra=True)


@api.post("/liveness", summary="Check which jobs are still open")
def liveness_start(request):
    if throttled(request.user, "liveness", settings.STILLOPEN_CHECKS_PER_HOUR):
        raise too_many()
    return _progress(liveness.start_run(request.user))


@api.get("/liveness/status", summary="Progress of the latest open/closed check")
def liveness_status(request):
    return _progress(liveness.current_run(request.user))
