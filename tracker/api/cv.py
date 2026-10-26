"""CV versions for the new app. Same rules as `views_cv.py`: versions are immutable (an edit is a new version), a tailored version with
claims the fact check could not find stays locked for download until the person approves it, and another person's version is a 404."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import CVVersion, SiteConfig
from ..services import ats, cvexport, cvgen, cvversions, languagetool
from ..services.cvversions import CVError
from ..services.throttle import throttled
from .common import owned, owned_job, throttle

router = Router()


def _version(request, cv_id) -> CVVersion:
    return get_object_or_404(CVVersion.objects.select_related("application", "parent"), pk=cv_id, owner=request.user)


def _job(version: CVVersion):
    app = version.application
    return {"id": app.pk, "role": app.role, "company": app.company} if app else None


def _summary(version: CVVersion) -> dict:
    return {
        "id": version.pk, "label": version.label, "kind": version.kind, "kind_label": version.get_kind_display(),
        "source": version.source, "source_label": version.get_source_display(), "provider": version.provider,
        "created_at": version.created_at.isoformat(), "job": _job(version),
        "flagged": version.flagged, "flagged_count": len(version.check_report or []), "approved": version.approved, "exportable": version.exportable,
        "ats_readiness": ats.cached_readiness(version.pk, version.content),
    }


def _downloads(version: CVVersion) -> dict | None:
    """Classic URLs of the files (they are not JSON), only once the version may be exported."""
    if not version.exportable:
        return None
    return {
        "docx": reverse("cv_download", args=[version.pk, "docx"]), "md": reverse("cv_download", args=[version.pk, "md"]),
        "print": reverse("cv_print", args=[version.pk]),
    }


class ExperienceIn(Schema):
    company: str = ""
    role: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = []


class EducationIn(Schema):
    school: str = ""
    degree: str = ""
    start: str = ""
    end: str = ""


class ProjectIn(Schema):
    name: str = ""
    description: str = ""


@router.get("/cv", summary="The person's CV versions: tailored ones and the master history")
def list_versions(request):
    config = SiteConfig.for_user(request.user)
    try:
        cvversions.ensure_master(request.user, config)  # first visit: the profile CV becomes version 1
    except CVError:
        pass
    versions = list(CVVersion.objects.filter(owner=request.user).select_related("application"))
    masters = [v for v in versions if v.kind == "master"]
    return {
        "masters": [{**_summary(v), "current": i == 0} for i, v in enumerate(masters)],
        "tailored": [_summary(v) for v in versions if v.kind == "tailored"],
    }


@router.get("/cv/{cv_id}", summary="One CV version with its text and fact-check results")
def get_version(request, cv_id: int):
    version = _version(request, cv_id)
    parent = version.parent if version.parent and version.parent.owner_id == request.user.pk else None
    return {
        **_summary(version),
        "content": version.content, "check_report": version.check_report or [], "approved_at": version.approved_at.isoformat() if version.approved_at else None,
        "job_snapshot": version.job_snapshot, "parent": {"id": parent.pk, "label": parent.label} if parent else None,
        "children": version.children.filter(owner=request.user).count(), "downloads": _downloads(version),
        "diff_url": f"/cv/{version.pk}/diff",
    }


@router.post("/cv/{cv_id}/writing-check", summary="Grammar/clarity check of this version's own text (LanguageTool, off unless the admin set one up)")
def writing_check(request, cv_id: int):
    version = _version(request, cv_id)
    config = SiteConfig.for_user(request.user)
    if not languagetool.available(config):
        raise HttpError(400, "Writing check is not set up on this server.")
    throttle(request, "writing-check", settings.STILLOPEN_CHECKS_PER_HOUR)
    try:
        matches = languagetool.check(version.content, config)
    except languagetool.LanguageToolError as exc:
        raise HttpError(400, str(exc))
    return {"matches": matches}


class EditIn(Schema):
    content: str
    label: str = ""


@router.post("/cv/{cv_id}/edit", summary="Save an edit as a new version")
def edit_version(request, cv_id: int, payload: EditIn):
    version = _version(request, cv_id)
    try:
        created = cvversions.new_version_from_edit(version, payload.content, SiteConfig.for_user(request.user), payload.label.strip()[:140])
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"id": created.pk, "changed": created.pk != version.pk}


@router.get("/cv/{cv_id}/diff", summary="Compare a version with another one (its parent by default)")
def diff_version(request, cv_id: int, against: int | None = None):
    version = _version(request, cv_id)
    if against is not None:
        other = owned(CVVersion, request, against)
    else:
        other = version.parent if version.parent and version.parent.owner_id == request.user.pk else cvversions.latest_master(request.user)
    choices = [{"id": c.pk, "label": c.label or c.get_kind_display()} for c in CVVersion.objects.filter(owner=request.user).exclude(pk=version.pk)[:50]]
    base = {"version": {"id": version.pk, "label": version.label}, "choices": choices}
    if other is None or other.pk == version.pk:
        return {**base, "other": None, "rows": []}
    rows = [{"tag": tag, "text": text} for tag, text in cvexport.line_diff(other.content, version.content)]
    return {**base, "other": {"id": other.pk, "label": other.label}, "rows": rows}


@router.post("/cv/{cv_id}/approve", summary="Say the flagged items are true, which unlocks downloads")
def approve_version(request, cv_id: int):
    version = _version(request, cv_id)
    cvversions.approve(version)
    return {"ok": True, "exportable": version.exportable}


@router.post("/cv/{cv_id}/restore", summary="Make an earlier master version the current CV again")
def restore_version(request, cv_id: int):
    version = _version(request, cv_id)
    try:
        created = cvversions.restore(version)
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"id": created.pk}


@router.delete("/cv/{cv_id}", summary="Delete a tailored version")
def delete_version(request, cv_id: int):
    version = _version(request, cv_id)
    try:
        cvversions.delete_tailored(version)
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True}


class TailorIn(Schema):
    mode: str = "auto"


@router.post("/jobs/{job_id}/tailor", summary="Tailor the CV for a job")
def tailor(request, job_id: int, payload: TailorIn):
    app = owned_job(request, job_id)
    if throttled(request.user, "cvgen", settings.STILLOPEN_CVGEN_PER_HOUR):
        raise HttpError(429, "Too many CV requests this hour. Try again later.")  # the classic page's own words
    mode = payload.mode if payload.mode in ("auto", "ai", "keywords") else "auto"
    try:
        version = cvgen.tailor(app, SiteConfig.for_user(request.user), mode)
    except CVError as exc:
        raise HttpError(400, str(exc))
    return {"id": version.pk, "flagged": version.flagged, "flagged_count": len(version.check_report or [])}
