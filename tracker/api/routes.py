from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import django_auth

from ..context import staff_flags
from ..models import Application, Bucket, JobSource, ScoreBand, SiteConfig, Status, UserProfile
from ..services import ai, board, careerops, geo, guide, knowledge, liveness, quiz, scan
from ..services import apply as apply_service
from ..services.cards import card_for
from ..services.pipeline import upcoming_interviews
from ..services.throttle import throttled
from .common import ApiFormError, owned_job, too_many

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


@api.exception_handler(ApiFormError)
def _form_errors(request, exc):
    return api.create_response(request, {"error": str(exc), "fields": exc.fields}, status=400)


owned = owned_job


class StatusIn(Schema):
    status: int


# --- who am I ------------------------------------------------------------------------------------

@api.get("/me", summary="The signed-in person")
def me(request):
    user = request.user
    site = SiteConfig.load()
    config = SiteConfig.for_user(user)
    flags = staff_flags(site) if user.is_staff else {}
    return {
        "id": user.pk,
        "name": guide.first_name(user),
        "email": user.email,
        "is_staff": user.is_staff,
        "greeting": guide.greeting(user, timezone.localtime()),
        "site_title": site.site_title,
        "prep_enabled": config.prep_enabled,
        "assistant_enabled": site.mcp_remote_enabled,
        "writing_check_enabled": bool(site.effective_languagetool_url),
        "translate_enabled": bool(site.effective_libretranslate_url),
        # the banners only a site admin sees (the same rule the classic pages used)
        "email_unverified_signups": bool(flags.get("email_unverified_signups")),
        "legal_has_blanks": bool(flags.get("legal_needs_attention")),
        "jooble_sources_dormant": bool(flags.get("jooble_sources_dormant")),
        "usajobs_sources_dormant": bool(flags.get("usajobs_sources_dormant")),
    }


# --- dashboard -----------------------------------------------------------------------------------

def _iso(value):
    return value.isoformat() if value else None


def _repost(signal) -> dict | None:
    if not signal:
        return None
    return {
        "distinct_urls": signal["distinct_urls"], "distinct_dates": signal["distinct_dates"],
        "first_seen": _iso(signal["first_seen"].date()), "last_seen": _iso(signal["last_seen"].date()),
    }


def _fit_badge(card, has_areas: bool) -> str | None:
    """Fits / Check fit always show; Fit unknown only when the person has told us where they would work (the classic rule)."""
    if card["fit_level"] == "warn":
        return "check"
    if card["fit_level"] == "ok":
        return "fits"
    return "unknown" if has_areas else None


def _job(card, has_areas: bool) -> dict:
    app = card["app"]
    cv = card["cv"]
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
        "risk": app.risk,
        "summary": app.summary,
        "next_action": app.next_action,
        "notes": app.notes,
        "source": app.source.name if app.source_id else "",
        "advertised_pay": app.advertised_pay,
        "location": app.location_text,
        "country": app.country,
        "country_name": geo.country_name(app.country) if app.country else "",
        "arrangement": app.arrangement,
        "found_date": app.found_date.isoformat(),
        "applied_date": _iso(app.applied_date),
        "applied_channel": app.get_applied_channel_display() if app.applied_channel else "",
        "applied_cv": {"id": app.applied_cv_id, "label": f"CV v{app.applied_cv_id}"} if app.applied_cv_id else None,
        "follow_up_date": _iso(app.follow_up_date),
        "counts_as_applied": app.status.counts_as_applied,
        "deadline": _iso(app.deadline),
        "days_left": card["days_left"],
        "urgent": card["urgent"],
        "overdue": card["overdue"],
        "live_state": app.live_state,
        "live_detail": app.live_detail,
        "strengths": [i.text for i in card["strengths"]],
        "gaps": [i.text for i in card["gaps"]],
        "fit_level": card["fit_level"],
        "fit_text": card["fit_text"],
        "fit_badge": _fit_badge(card, has_areas),
        "has_cv": cv is not None,
        "cv": {"id": cv.pk, "label": f"CV v{cv.pk}", "flagged": cv.flagged, "approved": cv.approved} if cv else None,
        "repost": _repost(card["repost"]),
        "skill_matched": card["skill_matched"],
        "tech_skills": card["tech_skills"],
        "evaluated": app.ai_evaluated_at is not None or app.score is not None,
        "ai_evaluated": app.ai_evaluated_at is not None,
        "ai_method": app.ai_method,
        "has_description": bool(app.description),
        "documents": [
            {"id": d.pk, "kind": d.kind.name, "title": d.title, "paperless_id": d.paperless_id, "paperless_error": d.paperless_error}
            for d in card["documents"]
        ],
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
    candidate_text = knowledge.all_candidate_text(config, user)
    cards = []
    for app in apps:
        card = card_for(app, config, bands, areas, profile, candidate_text)
        card["bucket_key"] = app.effective_bucket(config).key
        cards.append(card)
    cards.sort(key=lambda c: (0 if c["urgent"] else 1, -(c["percent"] if c["percent"] is not None else -1)))
    scored = [c["percent"] for c in cards if c["percent"] is not None]
    submitted = [c for c in cards if c["app"].status.counts_as_applied]
    scan_run = scan.current_run(user)
    has_areas = bool(areas)
    next_step = guide.next_step(
        profile, cards, has_areas=has_areas,
        searching=bool(scan_run and scan_run.running),
        prep_due=quiz.due_plans(user) if config.prep_enabled else None,
    )
    checked = [c["app"].live_checked_at for c in cards if c["app"].live_checked_at]
    # Drafts the scheduled search prepared (Draft ahead) that the person has not approved or discarded; read from the
    # versions already prefetched on each job, so this adds no queries.
    drafts = sorted(
        ((c["app"], v) for c in cards for v in c["app"].cv_versions.all() if v.draft_ahead and v.kind == "tailored" and not v.approved),
        key=lambda pair: (pair[1].created_at, pair[1].pk), reverse=True,
    )
    paperless_on = user.is_staff and config.paperless_enabled and bool(config.effective_paperless_url)
    return {
        "greeting": guide.greeting(user, timezone.localtime()),
        "buckets": [{"key": b.key, "label": b.label, "description": b.description, "is_closed": b.is_closed} for b in buckets],
        "statuses": [
            {"id": s.pk, "name": s.name, "bucket_key": s.bucket.key, "color": s.color, "counts_as_applied": s.counts_as_applied}
            for s in statuses
        ],
        "band_labels": [b.label for b in bands],
        "jobs": [_job(c, has_areas) for c in cards],
        "stats": {
            "total": len(cards),
            "submitted": len(submitted),
            "average_match": round(sum(scored) / len(scored)) if scored else None,
            "urgent": sum(1 for c in cards if c["urgent"]),
        },
        "followups": [
            {
                "id": a.pk, "company": a.company, "role": a.role, "follow_up_date": a.follow_up_date.isoformat(),
                "applied_date": _iso(a.applied_date),
            }
            for a in apply_service.due_followups(user)
        ],
        "upcoming_interviews": [
            {
                "id": i.pk, "when": i.scheduled_at.isoformat(), "kind": i.get_kind_display(),
                "company": i.application.company, "role": i.application.role, "job_id": i.application_id,
            }
            for i in upcoming_interviews(user)
        ],
        "drafts": [
            {
                "id": v.pk, "job_id": a.pk, "company": a.company, "role": a.role,
                "flagged_count": len(v.check_report or []), "created_at": _iso(v.created_at),
            }
            for a, v in drafts[:10]
        ],
        "next_step": next_step,
        "can_scan": JobSource.for_user(user, enabled=True).exists(),
        "checked_at": _iso(max(checked)) if checked else None,
        "has_areas": has_areas,
        "urgent_days": config.urgent_days,
        "prep_enabled": config.prep_enabled,
        "judge_label": config.get_ai_provider_display(),
        "paperless_on": paperless_on,
        "paperless_url": config.effective_paperless_url if paperless_on else "",
        "can_import": user.is_staff and bool(config.careerops_path),
        "scan": _scan_payload(scan_run) if scan_run else None,
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


def _scan_payload(run) -> dict:
    """A search run as the dashboard's search card needs it: progress, the plain note, and what each source gave."""
    if run is None:
        return {**_progress(None, extra=True), "note": "", "started_at": None, "finished_at": None, "phase": "done", "entries": []}
    phase = "done" if not run.running else "sorting" if run.total > 0 and run.done >= run.total else "reading"
    return {
        **_progress(run, extra=True),
        "note": run.note, "started_at": _iso(run.started_at), "finished_at": _iso(run.finished_at), "phase": phase,
        "entries": [
            {
                "source": e.source_name, "connector": e.get_connector_display(), "found": e.found, "matched": e.matched,
                "added": e.added, "duplicates": e.duplicates, "outside": e.outside, "error": e.error,
            }
            for e in run.entries.all()
        ],
    }


@api.post("/scan", summary="Search for new jobs")
def scan_start(request):
    if throttled(request.user, "scan", settings.STILLOPEN_SCANS_PER_HOUR):
        raise too_many()
    return _scan_payload(scan.start_run(request.user))


@api.get("/scan/status", summary="Progress of the person's latest search")
def scan_status(request):
    return _scan_payload(scan.current_run(request.user))


@api.post("/liveness", summary="Check which jobs are still open")
def liveness_start(request):
    if throttled(request.user, "liveness", settings.STILLOPEN_CHECKS_PER_HOUR):
        raise too_many()
    return _progress(liveness.start_run(request.user))


@api.get("/liveness/status", summary="Progress of the latest open/closed check")
def liveness_status(request):
    return _progress(liveness.current_run(request.user))


# --- career-ops import (site admins only) ---------------------------------------------------------------------

@api.post("/import", summary="Import the career-ops tracker, reports and PDFs (site admins only)")
def import_tracker(request):
    if not request.user.is_staff:
        raise HttpError(403, "Only site admins can do that.")
    try:
        counts = careerops.import_all(SiteConfig.for_user(request.user), request.user)
    except careerops.ImportErrorMessage as exc:
        raise HttpError(400, str(exc))
    return {"ok": True, **counts, "message": f"Imported: {counts.get('created', 0)} new, {counts.get('updated', 0)} refreshed"}


# --- the rest of the app: every other module in this package that defines `router` is mounted here ---------

import importlib  # noqa: E402
import pkgutil  # noqa: E402

for _info in pkgutil.iter_modules(importlib.import_module(__package__).__path__):
    if _info.name in ("routes", "common"):
        continue
    _module = importlib.import_module(f"{__package__}.{_info.name}")
    if hasattr(_module, "router"):
        api.add_router("", _module.router)
