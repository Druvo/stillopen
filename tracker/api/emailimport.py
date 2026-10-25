"""Jobs from a person's own job-alert email, for the new app. The person pastes the email (or chooses an .eml file); nothing is fetched from
LinkedIn, Indeed or anyone else, and no link in the email is ever opened. `?preview=1` says what was found; the real call adds the rows the
person left ticked. Owner-only: it only ever reads the pasted text and writes the signed-in person's own tracker."""
import json

from ninja import Router
from ninja.errors import HttpError

from ..services import emailimport
from .common import throttle

router = Router()


def _selected(raw) -> list[int] | None:
    """The row numbers the person left ticked: a JSON list, or "1,2,3" / repeated form values. None = the field was not sent."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list) and all(isinstance(v, str) for v in raw):  # "1,2,3", or repeated form values
        raw = [p for v in raw for p in v.replace(" ", "").split(",") if p != ""]
    if not isinstance(raw, list):
        raise HttpError(400, "We could not read which jobs were ticked. Please try again.")
    try:
        return [int(v) for v in raw]
    except (TypeError, ValueError):
        raise HttpError(400, "We could not read which jobs were ticked. Please try again.") from None


def _payload(request) -> tuple[str, str, bytes | None, list[int] | None]:
    if (request.content_type or "").startswith("multipart/form-data"):
        upload = request.FILES.get("file")
        raw = None
        if upload is not None:
            if upload.size > emailimport.MAX_BYTES:
                raise HttpError(400, "That email is bigger than 500 KB. Paste just the part with the jobs.")
            raw = upload.read(emailimport.MAX_BYTES + 1)
        selected = request.POST.getlist("selected")
        return request.POST.get("text", ""), request.POST.get("html", ""), raw, (_selected(selected) if "selected" in request.POST else None)
    if len(request.body or b"") > emailimport.MAX_BYTES * 3:
        raise HttpError(400, "That is bigger than 500 KB. Paste just the part of the email with the jobs.")
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        raise HttpError(400, "We could not read what was sent. Please try again.") from None
    if not isinstance(body, dict):
        raise HttpError(400, "We could not read what was sent. Please try again.")
    text, html = body.get("text") or "", body.get("html") or ""
    if not isinstance(text, str) or not isinstance(html, str):
        raise HttpError(400, "We could not read what was sent. Please try again.")
    return text, html, None, _selected(body.get("selected"))


@router.post("/jobs/import-email", summary="Find the jobs in a job-alert email the person pasted or saved as .eml (preview=1 only says what was found). Nothing is fetched")
def import_email(request, preview: int = 0):
    throttle(request, "emailimport", emailimport.hourly_limit())
    text, html, raw, selected = _payload(request)
    try:
        found = emailimport.read(text=text, html=html, eml=raw)
    except emailimport.EmailProblem as exc:
        raise HttpError(400, str(exc)) from None
    if preview:
        return emailimport.check(request.user, found)
    if selected is not None and not selected:
        raise HttpError(400, "Tick at least one job to add.")
    if not found["rows"]:
        raise HttpError(400, found["problems"][0] if found["problems"] else "We could not find any jobs in that email.")
    return emailimport.add(request.user, found, selected)
