"""Calendar files (.ics, RFC 5545) for interviews, so a person can put them in Google, Apple or Outlook calendar.

Plain text, built here with no library: CRLF line ends, lines folded at 75 octets (never inside a UTF-8 character), `\\`, `;`, `,` and
newlines escaped in text values, times in UTC, a stable UID per interview (so adding it twice updates rather than duplicates), and two
reminders (one day and one hour before). Nothing leaves the server: the person downloads the file and opens it themselves.
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

PRODID = "-//StillOpen//Interviews//EN"
CRLF = "\r\n"

# How long an interview usually lasts, by kind, when nobody said (minutes).
DEFAULT_MINUTES = {"phone": 30, "video": 60, "technical": 90, "onsite": 180, "final": 90, "other": 60}
FALLBACK_MINUTES = 60
ALARMS = [("-P1D", "Interview tomorrow"), ("-PT1H", "Interview in one hour")]


def escape_text(value: str) -> str:
    """A TEXT value as RFC 5545 section 3.3.11 wants it: backslash, semicolon and comma escaped, line breaks as \\n, control characters dropped."""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch >= " " and ch != "\x7f")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_line(line: str) -> str:
    """Fold one content line so no physical line is longer than 75 octets (the leading space of a continuation counts). Splits only between characters."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts: list[str] = []
    current = b""
    limit = 75
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
            limit = 74  # room for the space that starts every continuation line
        current += encoded
    parts.append(current.decode("utf-8"))
    return (CRLF + " ").join(parts)


def utc_stamp(moment: dt.datetime) -> str:
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def duration_minutes(interview) -> int:
    return DEFAULT_MINUTES.get(interview.kind, FALLBACK_MINUTES)


def summary(interview) -> str:
    app = interview.application
    return f"Interview: {app.role} at {app.company}"


def description(interview) -> str:
    lines = [f"Kind: {interview.get_kind_display()}"]
    if interview.where:
        lines.append(f"Where: {interview.where}")
    if interview.notes.strip():
        lines += ["", "Notes:", interview.notes.strip()]
    return "\n".join(lines)


def event_lines(interview, now: dt.datetime | None = None) -> list[str]:
    """The VEVENT (with its two VALARMs) for one interview, unfolded."""
    start = interview.scheduled_at
    end = start + dt.timedelta(minutes=duration_minutes(interview))
    lines = [
        "BEGIN:VEVENT",
        f"UID:interview-{interview.pk}@stillopen",
        f"DTSTAMP:{utc_stamp(now or timezone.now())}",
        f"DTSTART:{utc_stamp(start)}",
        f"DTEND:{utc_stamp(end)}",
        f"SUMMARY:{escape_text(summary(interview))}",
        f"DESCRIPTION:{escape_text(description(interview))}",
    ]
    if interview.where:
        lines.append(f"LOCATION:{escape_text(interview.where)}")
    lines += ["STATUS:CONFIRMED", "TRANSP:OPAQUE"]
    for trigger, text in ALARMS:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape_text(text)}", f"TRIGGER:{trigger}", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def calendar(interviews, name: str = "StillOpen interviews", now: dt.datetime | None = None) -> str:
    """A whole VCALENDAR for the given interviews (possibly none), CRLF-terminated and folded."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{escape_text(name)}"]
    for interview in interviews:
        lines += event_lines(interview, now)
    lines.append("END:VCALENDAR")
    return CRLF.join(fold_line(line) for line in lines) + CRLF
