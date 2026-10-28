"""A minimal iCalendar (RFC 5545) writer: text escaping, 75-octet line folding, timed and all-day events. No dependencies."""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

CRLF = "\r\n"


def escape(text: str) -> str:
    """Escape a TEXT value; control characters (including line breaks) become spaces so nothing can start a new property."""
    text = "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in str(text))
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after one space; never split inside a UTF-8 character."""
    out, current, size = [], "", 0
    for ch in line:
        width = len(ch.encode())
        if size + width > (75 if not out else 74):
            out.append(current)
            current, size = "", 0
        current += ch
        size += width
    out.append(current)
    return (CRLF + " ").join(out)


def _utc(value: datetime) -> str:
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event(uid: str, summary: str, *, stamp: datetime, start, minutes: int = 60) -> list[str]:
    """One VEVENT. A `date` start makes an all-day event; a `datetime` start a timed one lasting `minutes`."""
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{_utc(stamp)}"]
    if isinstance(start, datetime):
        lines += [f"DTSTART:{_utc(start)}", f"DTEND:{_utc(start + timedelta(minutes=minutes))}"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}", "TRANSP:TRANSPARENT"]
    lines += [f"SUMMARY:{escape(summary)}", "END:VEVENT"]
    return lines


def calendar(name: str, events: list[list[str]]) -> str:
    head = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StillOpen//Job search calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H",
    ]
    lines = head + [line for ev in events for line in ev] + ["END:VCALENDAR"]
    return CRLF.join(fold(line) for line in lines) + CRLF
