"""Looking after the jobs a person tracks: taking one off, acting on several at once, undoing a move, the history of a job, a spreadsheet in,
and reading a pasted reply.

The same rules as everywhere: every job is the signed-in person's own (another person's id is a 404, and in a bulk call one foreign id makes
the whole call a 404 with nothing changed), nothing here contacts an employer, and pasted text is data that is read and thrown away."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import Application, Event, Status
from ..services import board, jobimport, linkedinexport, replyparse, tracking, tz
from .common import owned_job, throttle

router = Router()

BULK_MAX = 500
KIND_LABELS = {
    "note": "Note", "status": "Status", "applied": "Applied", "interview": "Interview", "followup": "Follow-up", "other": "Other",
}
HISTORY_CAP = 100


# --- take a job off the tracker ---------------------------------------------------------------------

@router.get("/jobs/{job_id}/remove-preview", summary="What taking this job off the tracker would also remove")
def remove_preview(request, job_id: int):
    app = owned_job(request, job_id)
    return {"id": app.pk, "company": app.company, "role": app.role, **tracking.removal_preview(app)}


@router.delete("/jobs/{int:job_id}", summary="Remove a job, and what hangs off it, for good")
def remove_job(request, job_id: int):
    app = owned_job(request, job_id)
    try:
        tracking.remove_jobs(request.user, [app.pk])
    except tracking.TrackingError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True, "removed": 1}


# --- several at once ---------------------------------------------------------------------------------

class BulkIn(Schema):
    ids: list[int]
    action: str  # remove | status | preview | undo
    status_id: int | None = None


def _status_payload(status: Status) -> dict:
    return {"id": status.pk, "name": status.name, "label": board.label_for(status.name), "bucket_key": status.bucket.key}


@router.post("/jobs/bulk", summary="Remove several jobs, or move them to another status, in one go")
def bulk(request, payload: BulkIn):
    ids = list(dict.fromkeys(payload.ids))
    if not ids:
        raise HttpError(400, "Pick at least one job.")
    if len(ids) > BULK_MAX:
        raise HttpError(400, f"Pick up to {BULK_MAX} jobs at a time.")
    if payload.action not in ("remove", "status", "preview", "undo"):
        raise HttpError(400, "That is not something we can do to several jobs.")
    apps = list(Application.objects.filter(owner=request.user, pk__in=ids).select_related("status", "owner"))
    if len(apps) != len(ids):  # any id that is not theirs (or does not exist): nothing at all happens
        raise HttpError(404, "One of those jobs was not found.")
    if payload.action == "preview":
        return tracking.bulk_removal_preview(ids)
    if payload.action == "remove":
        try:
            count = tracking.remove_jobs(request.user, ids)
        except tracking.TrackingError as exc:
            raise HttpError(400, str(exc))
        return {"ok": True, "removed": count}
    if payload.action == "undo":
        return {"ok": True, "undone": [a.pk for a in apps if board.undo_status(a)]}
    if payload.status_id is None:
        raise HttpError(400, "Choose a status.")
    status = get_object_or_404(Status.objects.select_related("bucket"), pk=payload.status_id)
    changed = [a.pk for a in apps if board.change_status(a, status)]
    return {"ok": True, "changed": changed, "status": _status_payload(status)}


@router.post("/jobs/{job_id}/status/undo", summary="Undo the last status change of a job (within a few minutes)")
def undo_status(request, job_id: int):
    app = owned_job(request, job_id)
    if not board.undo_status(app):
        raise HttpError(400, f"It is too late to undo that. You can undo a move for {board.UNDO_MINUTES} minutes, as long as the job has not moved since.")
    app.refresh_from_db()
    return {"ok": True, "status": _status_payload(app.status)}


# --- history ---------------------------------------------------------------------------------------------

@router.get("/jobs/{job_id}/history", summary="What has happened to a job, newest first")
def history(request, job_id: int):
    app = owned_job(request, job_id)
    events = list(Event.objects.filter(application=app).order_by("-happened_at", "-id")[: HISTORY_CAP + 1])
    return {
        "items": [
            {
                "id": e.pk, "at": e.happened_at.isoformat(), "date": tz.local_date(e.happened_at, request.user).isoformat(),
                "kind": e.kind, "kind_label": KIND_LABELS.get(e.kind, "Note"), "text": e.text,
            }
            for e in events[:HISTORY_CAP]
        ],
        "capped": len(events) > HISTORY_CAP,
    }


# --- a spreadsheet in ----------------------------------------------------------------------------------------

@router.post("/jobs/import", summary="Add jobs from a spreadsheet saved as CSV, or from the person's own LinkedIn data export (.zip or its CSVs) (preview=1 only says what would happen)")
def import_jobs(request, preview: int = 0):
    throttle(request, "jobimport", getattr(settings, "STILLOPEN_IMPORTS_PER_HOUR", 30))
    upload = request.FILES.get("file")
    if upload is None:
        raise HttpError(400, "Choose a CSV file first.")
    is_zip = upload.name.lower().endswith(".zip")
    too_big = (
        "That file is bigger than 25 MB. Request only the Jobs part of your data from LinkedIn, or choose just the two CSV files from the zip."
        if is_zip else "That file is bigger than 1 MB. Split it into smaller files, or remove columns you do not need."
    )
    cap = linkedinexport.MAX_ZIP if is_zip else linkedinexport.MAX_ENTRY  # a long LinkedIn list may pass 1 MB; any other spreadsheet may not
    if upload.size > cap:
        raise HttpError(400, too_big)
    raw = upload.read(cap + 1)
    if not is_zip and len(raw) > jobimport.MAX_BYTES and not linkedinexport.is_linkedin_csv(raw):
        raise HttpError(400, too_big)
    try:
        if not is_zip and len(raw) > jobimport.MAX_BYTES:
            return linkedinexport.read(request.user, raw, preview=bool(preview))
        return jobimport.read_file(request.user, raw, preview=bool(preview))
    except jobimport.ImportProblem as exc:
        raise HttpError(400, str(exc))


# --- a reply the person pasted ------------------------------------------------------------------------------

class ReplyIn(Schema):
    text: str


@router.post("/jobs/{job_id}/reply-parse", summary="Read an employer's email the person pasted, and suggest a status. Changes nothing")
def reply_parse(request, job_id: int, payload: ReplyIn):
    app = owned_job(request, job_id)
    throttle(request, "replyparse", getattr(settings, "STILLOPEN_REPLYPARSE_PER_HOUR", 120))
    text = payload.text.strip()
    if not text:
        raise HttpError(400, "Paste the email first.")
    reading = replyparse.read(text)
    truncated = len(text) > replyparse.MAX_CHARS
    status = board.find_status(replyparse.STATUS_NAMES[reading["kind"]]) if reading["kind"] else None
    if status is None:
        return {
            "suggestion": None, "truncated": truncated,
            "message": "We could not tell from this message where things stand. You can still set the status yourself.",
        }
    return {
        "suggestion": {
            "status": _status_payload(status), "confidence": reading["confidence"], "quotes": reading["quotes"], "mixed": reading["mixed"],
            "already": app.status_id == status.pk,
        },
        "truncated": truncated,
        "message": "",
    }
