"""The apply assistant for the new app. Nothing here submits an application or sends a message: the person applies on the employer's site,
and `record` only notes what they did. Same rules as `views_apply.py`: a CV with flagged claims that is not approved is never offered, and
a CV that is not the person's own or was tailored for another job is refused."""
from datetime import date

from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import Application, CVVersion, SiteConfig
from ..services import apply as apply_service
from ..services import fit as fit_service
from ..services.apply import ApplyError
from .common import owned_job

router = Router()


def _version(v: CVVersion) -> dict:
    return {
        "id": v.pk, "label": v.label or v.get_kind_display(), "kind": v.kind, "kind_label": v.get_kind_display(),
        "created": v.created_at.date().isoformat(), "flagged": bool(v.flagged),
        # file downloads and the print page stay on their classic addresses; the front end builds the in-app link to the CV itself
        "docx_url": reverse("cv_download", args=[v.pk, "docx"]), "print_url": reverse("cv_print", args=[v.pk]),
    }


@router.get("/jobs/{job_id}/apply", summary="Everything the apply assistant shows for one job")
def get_apply(request, job_id: int):
    app = owned_job(request, job_id)
    config = SiteConfig.for_user(request.user)
    versions = apply_service.sendable_versions(app)
    letters = list(app.cover_letters.all())
    return {
        "job": {
            "id": app.pk, "company": app.company, "role": app.role, "url": app.url, "closed": app.live_state == "expired",
            "applied": bool(app.applied_cv_id or app.applied_date), "applied_date": app.applied_date.isoformat() if app.applied_date else "",
            "channel": app.applied_channel, "note": app.applied_note,
            "follow_up_date": app.follow_up_date.isoformat() if app.follow_up_date else "",
        },
        "checks": apply_service.checklist(app, config, versions) + fit_service.fit_flags(app),
        "versions": [_version(v) for v in versions],
        "selected": versions[0].pk if versions else None,
        "has_flagged": CVVersion.objects.filter(owner=request.user, application=app).exists() and not any(v.kind == "tailored" for v in versions),
        "cover_letters": [
            {"id": l.pk, "created": l.created_at.date().isoformat(), "needs_review": bool(l.flagged and not l.approved)}
            for l in letters
        ],
        "draft": apply_service.email_draft(app),
        "channels": [{"value": v, "label": label} for v, label in Application.CHANNELS if v],
        "followup_days": config.apply_followup_days,
        "max_followup_days": apply_service.MAX_FOLLOW_UP_DAYS,
    }


class RecordIn(Schema):
    cv: int | None = None  # a CV version; none = "I am sending a different CV"
    channel: str = ""
    note: str = ""
    days: int | None = None
    applied_on: str | None = None
    confirm_closed: bool = False


@router.post("/jobs/{job_id}/applied", summary="Record that the person applied (it never applies for them)")
def record(request, job_id: int, payload: RecordIn):
    app = owned_job(request, job_id)
    config = SiteConfig.for_user(request.user)
    if app.live_state == "expired" and not payload.confirm_closed:
        raise HttpError(400, "This posting looks closed. Tick the box to confirm you applied anyway.")
    version = get_object_or_404(CVVersion, pk=payload.cv, owner=request.user) if payload.cv else None
    try:
        applied_on = date.fromisoformat(payload.applied_on) if payload.applied_on else None
    except ValueError:
        raise HttpError(400, "Check the date and the number of days.")
    try:
        apply_service.record(app, version, payload.channel, payload.note, payload.days if payload.days is not None else config.apply_followup_days, config, applied_on)
    except ApplyError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True, "follow_up_date": app.follow_up_date.isoformat()}


@router.post("/jobs/{job_id}/followup/done", summary="Mark a follow-up as done")
def followup_done(request, job_id: int):
    apply_service.followup_done(owned_job(request, job_id))
    return {"ok": True}


class SnoozeIn(Schema):
    days: int = 3


@router.post("/jobs/{job_id}/followup/snooze", summary="Move a follow-up reminder to later")
def followup_snooze(request, job_id: int, payload: SnoozeIn):
    app = owned_job(request, job_id)
    apply_service.followup_snooze(app, payload.days)
    return {"ok": True, "follow_up_date": app.follow_up_date.isoformat()}
