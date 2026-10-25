"""How each job board answered the person's own searches: when it last worked and what went wrong when it did not.

Read from the per-source log lines every search writes (`ScanLogEntry`), only from this person's own search runs, so it shows nothing about
anyone else. The boards are matched by the name the log kept. Nothing here fetches anything."""
from tracker.models import ScanLogEntry, ScanRun

LOOK_BACK = 4000  # log lines read, newest first: far more than a month of searches


def health_by_name(user) -> dict[str, dict]:
    """{source name: {"state": "ok" | "error", "checked_at", "last_ok_at", "error", "since"}} for every source the person's searches have read.

    `error` is the newest error text and `since` is when the unbroken run of failures began (None while it is working)."""
    seen: dict[str, dict] = {}
    rows = ScanLogEntry.objects.filter(run__owner=user).order_by("-id").values_list("source_name", "error", "created_at")[:LOOK_BACK]
    for name, error, at in rows:
        entry = seen.get(name)
        if entry is None:
            seen[name] = entry = {
                "state": "error" if error else "ok", "checked_at": at, "last_ok_at": at if not error else None,
                "error": error or "", "since": at if error else None, "_streak": bool(error),
            }
            continue
        if error:
            if entry["_streak"]:
                entry["since"] = at  # still the same unbroken run of failures, one step further back
        else:
            entry["_streak"] = False
            if entry["last_ok_at"] is None:
                entry["last_ok_at"] = at
    for entry in seen.values():
        entry.pop("_streak", None)
    return seen


def public_health(entry: dict | None) -> dict:
    """The health of one source as the API shows it (dates as ISO text); a source no search has read yet is "unknown"."""
    if entry is None:
        return {"state": "unknown", "checked_at": None, "last_ok_at": None, "error": "", "since": None}
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {"state": entry["state"], "checked_at": iso(entry["checked_at"]), "last_ok_at": iso(entry["last_ok_at"]), "error": entry["error"], "since": iso(entry["since"])}


def last_search_trouble(user) -> dict | None:
    """How many sources had trouble in the person's latest finished search: {"total", "trouble"}, or None when they have not searched yet."""
    run = ScanRun.objects.filter(owner=user, running=False).order_by("-started_at", "-id").first()
    if run is None:
        return None
    entries = list(run.entries.values_list("error", flat=True))
    if not entries:
        return None
    return {"total": len(entries), "trouble": sum(1 for e in entries if e)}
