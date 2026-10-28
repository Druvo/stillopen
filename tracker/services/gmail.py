"""Gmail for one person's own connected account: send an application they have previewed in full, and read the replies in that one conversation.

THE ONLY PLACE THE APP SENDS A MESSAGE FOR A PERSON. The one sending function, `send_message`, is called from one API route that needs the
person's explicit confirmation of a digest of the exact message (recipient, subject, body, attachments) they were just shown. Nothing here is
ever called by the scheduler, a management command, the MCP server or an AI client (tests in tests_google.py walk the source to keep it so).
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import re
from email.message import EmailMessage
from email.utils import parseaddr

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from tracker.models import Application, CoverLetter, CVVersion, Event, GoogleConnection, MailMessage, SiteConfig
from tracker.services import apply as apply_service
from tracker.services import cvexport, googleconnect
from tracker.services.googleconnect import SCOPE_READ, SCOPE_SEND, GoogleError

API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_BODY = 20000
MAX_SNIPPET = 300
KEEP_MESSAGES = 100  # per job
CACHE_SECONDS = 120

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def posting_address(app: Application) -> str:
    """The apply address the posting itself publishes (first email in its text), or "". Never guessed from the company name."""
    match = _EMAIL.search(app.description or "")
    return match.group(0) if match else ""


def clean_address(value: str) -> str:
    value = (value or "").strip()
    name, address = parseaddr(value)
    if not address or address != value or any(c in value for c in "\r\n,;<> "):
        raise GoogleError("Type one email address to send to.")
    try:
        validate_email(address)
    except ValidationError:
        raise GoogleError("That email address does not look right.") from None
    return address


def _attachments(owner, app: Application, cv_id, cover_id) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    if cv_id:
        allowed = {v.pk: v for v in apply_service.sendable_versions(app)}
        version = allowed.get(cv_id)
        if version is None:  # unknown, someone else's, tailored for another job, or flagged and not approved
            raise GoogleError("That CV cannot be attached: it is not yours for this job, or it still has flagged claims to review.")
        files.append((f"CV-v{version.pk}.docx", cvexport.to_docx(version.content)))
    if cover_id:
        letter = CoverLetter.objects.filter(pk=cover_id, owner=owner, application=app).first()
        if letter is None or not letter.exportable:
            raise GoogleError("That cover letter cannot be attached: it is not yours for this job, or it still has flagged claims to review.")
        files.append((f"Cover-letter-{letter.pk}.docx", cvexport.to_docx(letter.content)))
    if sum(len(data) for _, data in files) > MAX_ATTACHMENT_BYTES:
        raise GoogleError("The attachments are too large to send (5 MB at most).")
    return files


def _digest(to: str, subject: str, body: str, cv_id, cover_id, files) -> str:
    h = hashlib.sha256()
    for part in (to, subject, body, str(cv_id or ""), str(cover_id or "")):
        h.update(part.encode())
        h.update(b"\x00")
    for name, data in files:
        h.update(name.encode() + b"\x00" + hashlib.sha256(data).digest())
    return h.hexdigest()


def prepare(owner, app: Application, to: str, subject: str, body: str, cv_id=None, cover_id=None) -> dict:
    """Validate and describe the exact message that would be sent. Sends nothing. The `digest` goes back with the confirm."""
    googleconnect.require(owner, SCOPE_SEND)
    to = clean_address(to)
    subject = (subject or "").strip()
    body = (body or "").replace("\x00", "").strip()
    if not subject or "\n" in subject or "\r" in subject or len(subject) > 200:
        raise GoogleError("Give the email a one-line subject (200 characters at most).")
    if not body or len(body) > MAX_BODY:
        raise GoogleError("Write the message: it cannot be empty or longer than 20,000 characters.")
    files = _attachments(owner, app, cv_id, cover_id)
    return {
        "to": to, "subject": subject, "body": body, "cv": cv_id or None, "cover": cover_id or None,
        "attachments": [{"name": name, "bytes": len(data)} for name, data in files],
        "digest": _digest(to, subject, body, cv_id, cover_id, files), "_files": files,
    }


def build_mime(sender: str, to: str, subject: str, body: str, files) -> bytes:
    msg = EmailMessage()
    if sender:
        msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    for name, data in files:
        msg.add_attachment(data, maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=name)
    return msg.as_bytes()


def send_message(owner, app: Application, to: str, subject: str, body: str, cv_id, cover_id, digest: str, confirm: bool,
                 channel_note: str = "") -> dict:
    """Send ONE previewed message from the person's own Gmail, then record it exactly like `apply.record`. Refuses without the confirm and the matching digest."""
    if confirm is not True:
        raise GoogleError("Nothing was sent. Press Send on the preview to confirm.")
    prepared = prepare(owner, app, to, subject, body, cv_id, cover_id)
    if not digest or digest != prepared["digest"]:
        raise GoogleError("The message changed since you looked at it. Preview it again, then press Send.")
    connection = googleconnect.require(owner, SCOPE_SEND)
    raw = base64.urlsafe_b64encode(build_mime(connection.email, prepared["to"], prepared["subject"], prepared["body"], prepared["_files"])).decode()
    payload: dict = {"raw": raw}
    if app.gmail_thread_id:
        payload["threadId"] = app.gmail_thread_id
    sent = googleconnect.api(connection, "POST", f"{API}/messages/send", json=payload)
    thread_id = str(sent.get("threadId", ""))[:64]
    # Recording is the same code the manual "I applied" button uses, so every rule it has applies here too.
    version = CVVersion.objects.filter(pk=cv_id, owner=owner).first() if cv_id else None
    config = SiteConfig.for_user(owner)
    apply_service.record(app, version, "email", channel_note or f"Sent from my Gmail to {prepared['to']}", config.apply_followup_days, config)
    if thread_id:
        app.gmail_thread_id = thread_id
        app.save(update_fields=["gmail_thread_id"])
    Event.objects.create(application=app, kind="applied", text=f"Email sent from your Gmail to {prepared['to']}: {prepared['subject']}"[:500])
    return {"thread_id": thread_id, "to": prepared["to"]}


# --- replies -----------------------------------------------------------------------------------------

def _header(message: dict, name: str) -> str:
    for h in (message.get("payload") or {}).get("headers", []) or []:
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value", ""))
    return ""


def _find_thread(connection: GoogleConnection, address: str) -> str:
    """The most recent conversation with one person-confirmed address (from or to it). Looks nowhere else."""
    address = clean_address(address)
    data = googleconnect.api(connection, "GET", f"{API}/threads", params={"q": f"from:{address} OR to:{address}", "maxResults": 1})
    threads = data.get("threads") or []
    return str(threads[0].get("id", ""))[:64] if threads else ""


def check_replies(owner, app: Application, contact_email: str = "", force: bool = False) -> dict:
    """Read the messages of this job's stored conversation we have not seen yet. Keeps sender, date, a short snippet and the id only."""
    connection = googleconnect.require(owner, SCOPE_READ)
    now = timezone.now()
    if not force and app.gmail_checked_at and (now - app.gmail_checked_at).total_seconds() < CACHE_SECONDS and not contact_email:
        return {"new": 0, "cached": True, "messages": messages_for(app)}
    if not app.gmail_thread_id:
        if not contact_email:
            return {"new": 0, "cached": False, "messages": [], "linked": False}
        app.gmail_thread_id = _find_thread(connection, contact_email)
        if not app.gmail_thread_id:
            app.gmail_checked_at = now
            app.save(update_fields=["gmail_checked_at"])
            return {"new": 0, "cached": False, "messages": [], "linked": False}
        app.save(update_fields=["gmail_thread_id"])
    thread = googleconnect.api(connection, "GET", f"{API}/threads/{app.gmail_thread_id}", params=[("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Date")])
    known = set(MailMessage.objects.filter(application=app).values_list("gmail_id", flat=True))
    me = (connection.email or "").lower()
    created = 0
    for message in (thread.get("messages") or [])[-KEEP_MESSAGES:]:
        gid = str(message.get("id", ""))[:64]
        if not gid or gid in known:
            continue
        sender = _header(message, "From")[:300]
        try:
            sent_at = dt.datetime.fromtimestamp(int(message.get("internalDate", 0)) / 1000, tz=dt.timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            sent_at = now
        MailMessage.objects.create(
            owner=owner, application=app, gmail_id=gid, sender=sender, sent_at=sent_at,
            snippet=html.unescape(str(message.get("snippet", "")))[:MAX_SNIPPET],
            from_me=bool(me and me in parseaddr(sender)[1].lower()),
        )
        created += 1
    app.gmail_checked_at = now
    app.save(update_fields=["gmail_checked_at"])
    if created:
        Event.objects.create(application=app, kind="note", text=f"{created} new message{'s' if created != 1 else ''} in your Gmail conversation for this job.")
    return {"new": created, "cached": False, "messages": messages_for(app), "linked": True}


def messages_for(app: Application) -> list[dict]:
    return [
        {"id": m.pk, "sender": m.sender, "sent_at": m.sent_at.isoformat(), "snippet": m.snippet, "from_me": m.from_me}
        for m in MailMessage.objects.filter(application=app).order_by("sent_at", "id")
    ]

