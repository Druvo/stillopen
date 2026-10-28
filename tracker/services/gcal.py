"""Google Calendar for one person's own connected account: keep interviews in step both ways, and offer free times.

Only events THIS app created are ever read back, changed or deleted (we keep the event id on the `Interview`); every other event on the calendar
is never touched. When Google's copy changed since our last sync, Google's time wins (or a cancellation marks the interview cancelled).
Nothing here sends mail: an event is created without guests, so Google never emails anyone.
"""
from __future__ import annotations

import datetime as dt
import logging
from urllib.parse import quote

from django.utils import timezone

from tracker.models import GoogleConnection, Interview
from tracker.services import googleconnect, tz
from tracker.services.googleconnect import SCOPE_BUSY, SCOPE_EVENTS, GoogleError

log = logging.getLogger(__name__)
CAL = "https://www.googleapis.com/calendar/v3"
EVENTS = f"{CAL}/calendars/primary/events"
SYNC_CACHE_SECONDS = 300
DURATION = dt.timedelta(hours=1)
WORK_START, WORK_END = 9, 17
SLOT_DAYS = 10


def _sync_on(owner) -> GoogleConnection | None:
    connection = googleconnect.for_user(owner)
    if connection and connection.calendar_sync and SCOPE_EVENTS in (connection.scopes or []):
        return connection
    return None


def _utc(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body(item: Interview) -> dict:
    app = item.application
    return {
        "summary": f"{item.get_kind_display()}: {app.role} at {app.company}"[:250],
        "location": (item.where or "")[:300],
        "description": f"Added by StillOpen for your application to {app.company}."[:500],
        "start": {"dateTime": _utc(item.scheduled_at), "timeZone": "UTC"},
        "end": {"dateTime": _utc(item.scheduled_at + DURATION), "timeZone": "UTC"},
        "extendedProperties": {"private": {"stillopen": "1"}},
        "reminders": {"useDefault": True},
    }


def push(item: Interview) -> str:
    """Create or update the calendar event of one interview, when the person has the sync on. Returns a plain-words note ("" when fine or off)."""
    connection = _sync_on(item.owner)
    if connection is None:
        return ""
    try:
        if item.outcome == "cancelled":
            return remove(item)
        if item.google_event_id:
            data = googleconnect.api(connection, "PATCH", f"{EVENTS}/{quote(item.google_event_id, safe='')}", json=_body(item))
        else:
            data = googleconnect.api(connection, "POST", EVENTS, json=_body(item), params={"sendUpdates": "none"})
        item.google_event_id = str(data.get("id", item.google_event_id))[:128]
        item.google_event_updated = str(data.get("updated", ""))[:40]
        item.save(update_fields=["google_event_id", "google_event_updated"])
        return ""
    except GoogleError as exc:
        return f"Saved here, but your Google Calendar was not updated: {exc}"


def remove(item: Interview) -> str:
    """Delete the event this app created for the interview (called before the interview itself is deleted)."""
    connection = _sync_on(item.owner)
    if connection is None or not item.google_event_id:
        return ""
    try:
        googleconnect.api(connection, "DELETE", f"{EVENTS}/{quote(item.google_event_id, safe='')}", ok=(200, 204, 404, 410), params={"sendUpdates": "none"})
        item.google_event_id = ""
        item.google_event_updated = ""
        if item.pk:
            item.save(update_fields=["google_event_id", "google_event_updated"])
        return ""
    except GoogleError as exc:
        return f"Removed here, but the event is still on your Google Calendar: {exc}"


def _parse(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def pull(owner, force: bool = False) -> dict:
    """Bring changes made in Google back, for events we created only. Short cache so opening the Interviews screen is cheap."""
    connection = _sync_on(owner)
    if connection is None:
        return {"changed": 0, "checked": 0, "cached": False, "note": ""}
    now = timezone.now()
    if not force and connection.calendar_synced_at and (now - connection.calendar_synced_at).total_seconds() < SYNC_CACHE_SECONDS:
        return {"changed": 0, "checked": 0, "cached": True, "note": ""}
    changed = checked = 0
    note = ""
    items = Interview.objects.filter(owner=owner).exclude(google_event_id="").exclude(outcome="cancelled").select_related("application")
    for item in items[:200]:
        checked += 1
        try:
            event = googleconnect.api(connection, "GET", f"{EVENTS}/{quote(item.google_event_id, safe='')}", ok=(200, 404, 410))
        except GoogleError as exc:
            note = str(exc)
            break
        if not event.get("id") or event.get("status") == "cancelled":
            item.outcome = "cancelled"
            item.save(update_fields=["outcome"])
            changed += 1
            continue
        if str(event.get("updated", "")) == item.google_event_updated:
            continue  # nothing changed in Google since we last wrote it
        start = _parse((event.get("start") or {}).get("dateTime", ""))
        item.google_event_updated = str(event.get("updated", ""))[:40]
        fields = ["google_event_updated"]
        if start and start != item.scheduled_at:
            item.scheduled_at = start
            fields.append("scheduled_at")
            changed += 1
        item.save(update_fields=fields)
    connection.calendar_synced_at = now
    connection.last_error = note[:300]
    connection.save(update_fields=["calendar_synced_at", "last_error"])
    return {"changed": changed, "checked": checked, "cached": False, "note": note}


def push_all(owner) -> dict:
    """Put every upcoming interview of the person on their calendar (used right after they switch the sync on)."""
    added = 0
    note = ""
    for item in Interview.objects.filter(owner=owner, outcome="pending", scheduled_at__gte=timezone.now()).select_related("application", "owner")[:100]:
        if item.google_event_id:
            continue
        note = push(item) or note
        added += 1 if item.google_event_id else 0
    return {"added": added, "note": note}


# --- free times -----------------------------------------------------------------------------------------

def free_slots(owner, count: int = 3, days: int = SLOT_DAYS) -> list[dt.datetime]:
    """Up to `count` one-hour slots, on different weekdays, between 09:00 and 17:00 in the person's own zone within the next `days` days."""
    connection = googleconnect.require(owner, SCOPE_BUSY)
    zone = tz.zone_for(owner)
    now = timezone.now().astimezone(zone)
    start = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=days)
    data = googleconnect.api(connection, "POST", f"{CAL}/freeBusy", json={"timeMin": _utc(now), "timeMax": _utc(end), "items": [{"id": "primary"}]})
    busy = []
    for block in ((data.get("calendars") or {}).get("primary") or {}).get("busy", []) or []:
        b_start, b_end = _parse(block.get("start", "")), _parse(block.get("end", ""))
        if b_start and b_end:
            busy.append((b_start, b_end))
    slots: list[dt.datetime] = []
    day = start
    while day < end and len(slots) < count:
        if day.weekday() < 5:
            for hour in (10, 14, 11, 15, 9, 16, 12, 13):  # mid-morning and mid-afternoon first
                if not WORK_START <= hour < WORK_END:
                    continue
                slot = day.replace(hour=hour)
                if all(slot + DURATION <= b0 or slot >= b1 for b0, b1 in busy):
                    slots.append(slot)
                    break
        day += dt.timedelta(days=1)
    return slots


def suggestion_text(owner, slots: list[dt.datetime]) -> str:
    if not slots:
        return ""
    zone_name = getattr(tz.zone_for(owner), "key", "") or timezone.get_current_timezone_name()
    lines = ["I am free at these times (" + zone_name + "):"]
    lines += [f"- {s:%A %d %B}, {s:%H:%M} to {(s + DURATION):%H:%M}" for s in slots]
    lines.append("Let me know which suits you, or suggest another time.")
    return "\n".join(lines)
