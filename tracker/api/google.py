"""The opt-in Google connection for the signed-in person: connect and disconnect, send ONE previewed application from their Gmail,
replies next to the job, a draft reply, free interview times, and the Calendar sync controls.

Sending is the one exception to "the app never sends a message", and it is as narrow as it can be: `send` needs the digest of the exact
message the person was just shown (`preview`) and an explicit `confirm: true`, goes from their own account to the one address they typed
or confirmed, and nothing else in the app (scheduler, commands, the MCP server) can reach it. No token is ever returned by any route."""
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import MailMessage
from ..services import apply as apply_service
from ..services import gcal, gmail, googleconnect, googledraft
from ..services.googleconnect import GoogleError
from .common import owned_job, throttle

router = Router()
SEND_PER_HOUR = 30
CHECK_PER_HOUR = 120
DRAFT_PER_HOUR = 30


def _fail(exc: Exception) -> HttpError:
    return HttpError(400, str(exc))


def _state(request) -> dict:
    connection = googleconnect.for_user(request.user)
    flash = request.session.pop("google_flash", "") if hasattr(request, "session") else ""
    return {
        "available": googleconnect.available(),
        "connected": connection is not None,
        "email": connection.email if connection else "",
        "connected_at": connection.connected_at.isoformat() if connection else None,
        "calendar_sync": bool(connection and connection.calendar_sync),
        "problem": connection.last_error if connection else "",
        "message": flash,
    }


@router.get("/google/status", summary="Whether the person's Google account is connected, and what it is used for")
def status(request):
    return _state(request)


@router.post("/google/connect", summary="Start connecting the person's own Google account (returns Google's address to go to)")
def connect(request):
    throttle(request, "google_connect", 20)
    try:
        return {"url": googleconnect.begin(request)}
    except GoogleError as exc:
        raise _fail(exc)


@router.post("/google/disconnect", summary="Revoke the permission at Google and delete the stored tokens")
def disconnect(request):
    googleconnect.disconnect(request.user)
    return _state(request)


class SettingsIn(Schema):
    calendar_sync: bool


@router.patch("/google/settings", summary="Keep my Google Calendar in step with my interviews (on or off)")
def settings(request, payload: SettingsIn):
    connection = googleconnect.for_user(request.user)
    if connection is None:
        raise HttpError(400, "Connect your Google account first.")
    connection.calendar_sync = payload.calendar_sync
    connection.save(update_fields=["calendar_sync"])
    out = _state(request)
    if payload.calendar_sync:
        out["pushed"] = gcal.push_all(request.user)
    return out


@router.post("/google/calendar/sync", summary="Bring changes made in Google Calendar back (events this app created only)")
def calendar_sync(request, force: bool = False):
    throttle(request, "google_calendar", CHECK_PER_HOUR)
    return gcal.pull(request.user, force=force)


class MessageIn(Schema):
    to: str
    subject: str
    body: str
    cv: int | None = None
    cover: int | None = None


class SendIn(MessageIn):
    digest: str = ""
    confirm: bool = False


@router.post("/jobs/{job_id}/google/preview", summary="The exact message that would be sent, with its attachments. Sends nothing")
def preview(request, job_id: int, payload: MessageIn):
    app = owned_job(request, job_id)
    try:
        prepared = gmail.prepare(request.user, app, payload.to, payload.subject, payload.body, payload.cv, payload.cover)
    except GoogleError as exc:
        raise _fail(exc)
    prepared.pop("_files")
    connection = googleconnect.for_user(request.user)
    return {**prepared, "from": connection.email if connection else ""}


@router.post("/jobs/{job_id}/google/send", summary="Send the previewed message from the person's own Gmail (needs their confirm)")
def send(request, job_id: int, payload: SendIn):
    app = owned_job(request, job_id)
    throttle(request, "google_send", SEND_PER_HOUR)
    try:
        result = gmail.send_message(request.user, app, payload.to, payload.subject, payload.body, payload.cv, payload.cover, payload.digest, payload.confirm)
    except (GoogleError, apply_service.ApplyError) as exc:
        raise _fail(exc)
    return {"ok": True, **result, "follow_up_date": app.follow_up_date.isoformat() if app.follow_up_date else ""}


@router.get("/jobs/{job_id}/google/messages", summary="The messages saved from this job's Gmail conversation")
def messages(request, job_id: int):
    app = owned_job(request, job_id)
    connection = googleconnect.for_user(request.user)
    return {
        "connected": connection is not None, "linked": bool(app.gmail_thread_id),
        "messages": gmail.messages_for(app), "checked_at": app.gmail_checked_at.isoformat() if app.gmail_checked_at else None,
    }


class CheckIn(Schema):
    contact_email: str = ""
    force: bool = True


@router.post("/jobs/{job_id}/google/check", summary="Look for new replies in this job's Gmail conversation")
def check(request, job_id: int, payload: CheckIn):
    app = owned_job(request, job_id)
    throttle(request, "google_check", CHECK_PER_HOUR)
    try:
        return gmail.check_replies(request.user, app, payload.contact_email, force=payload.force)
    except GoogleError as exc:
        raise _fail(exc)


class DraftIn(Schema):
    message_id: int
    with_times: bool = False


@router.post("/jobs/{job_id}/google/draft", summary="A draft reply to an employer's message, to edit (never sent from here)")
def draft(request, job_id: int, payload: DraftIn):
    app = owned_job(request, job_id)
    throttle(request, "google_draft", DRAFT_PER_HOUR)
    times = ""
    try:
        if payload.with_times:
            times = gcal.suggestion_text(request.user, gcal.free_slots(request.user))
        out = googledraft.draft(request.user, app, payload.message_id, times)
    except (GoogleError, googledraft.DraftError) as exc:
        raise _fail(exc)
    return {**out, "times": times}


@router.post("/jobs/{job_id}/google/times", summary="Three free interview times in the next ten days, as text to paste")
def times(request, job_id: int):
    owned_job(request, job_id)
    throttle(request, "google_times", CHECK_PER_HOUR)
    try:
        slots = gcal.free_slots(request.user)
    except GoogleError as exc:
        raise _fail(exc)
    return {"text": gcal.suggestion_text(request.user, slots), "count": len(slots)}
