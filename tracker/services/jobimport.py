"""Bringing a spreadsheet of jobs into a person's tracker.

The file is plain CSV (export from Excel, Numbers or Google Sheets as "CSV"). Columns are found by their header names, in any order and in
any case, with the usual alternatives (title or position for role, link or url for the web address, and so on). Nothing here reads the links:
it never touches the network, and the description of a job is left empty for the person to add or for a later "check my fit".

A first pass (`read_file(..., preview)`) only says what would happen; the same call without preview does it. The rules are the same in both
passes, so what the preview promised is what the import does: rows without a company or role, with a bad date or a bad link are not
imported and are listed with the row number; a job the person already tracks (same link, or same company and role) or that repeats earlier in
the file is skipped and listed; the job limit stops the import with a plain message."""
import csv
import io
import re
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction

from tracker.models import Application, Event
from tracker.services import board, geo, tracking

MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000
SHOWN = 50  # rows listed back (to add, skipped, problems); the counts are always complete

SYNONYMS = {
    "company": {"company", "company name", "employer", "organisation", "organization", "firm"},
    "role": {"role", "title", "job title", "job", "position", "position title", "job role"},
    "url": {"link", "url", "job link", "job url", "posting", "posting link", "web address", "apply link", "website"},
    "status": {"status", "stage", "state"},
    "found": {"found", "found date", "date found", "date", "date added", "added", "added on"},
    "applied": {"applied", "applied date", "date applied", "applied on"},
    "follow_up": {"follow up", "follow-up", "followup", "follow up date", "follow-up date"},
    "deadline": {"deadline", "apply by", "closing date", "closes", "close date", "due"},
    "location": {"location", "place", "city", "where"},
    "country": {"country"},
    "notes": {"notes", "note", "comments", "comment", "remarks"},
}
DATE_FIELDS = {"found": "found date", "applied": "applied date", "follow_up": "follow-up date", "deadline": "deadline"}


class ImportProblem(Exception):
    """The whole file is unusable; the message says why in plain words."""


def _header_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower().replace("%", " percent ")).strip()


def decode(raw: bytes) -> str:
    if len(raw) > MAX_BYTES:
        raise ImportProblem("That file is bigger than 1 MB. Split it into smaller files, or remove columns you do not need.")
    if b"\x00" in raw[:4096]:
        raise ImportProblem("That does not look like a CSV file. In your spreadsheet, choose File > Save as (or Download) > CSV.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportProblem("We could not read the letters in that file. Save it as CSV (UTF-8) and try again.")


def parse_date(text: str) -> date | None:
    """A day from 2026-10-25 or 25/10/2026 (day first; dashes and dots work too). Blank is None; anything else raises ValueError."""
    text = (text or "").strip()
    if not text:
        return None
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?", text)
    dmy = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", text)
    try:
        if iso:
            return date(int(iso[1]), int(iso[2]), int(iso[3]))
        if dmy:
            return date(int(dmy[3]), int(dmy[2]), int(dmy[1]))
    except ValueError:
        pass
    raise ValueError(text)


def _table(text: str) -> tuple[dict, list[tuple[int, dict]]]:
    """(which header is which field, [(row number in the file, {field: text})]) for the data rows."""
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = max(",;\t", key=first_line.count) if first_line else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [(n, r) for n, r in enumerate(rows, start=1) if any(cell.strip() for cell in r)]
    if not rows:
        raise ImportProblem("That file is empty. Add a row for each job, with a header row on top.")
    header_number, header = rows[0]
    columns: dict[int, str] = {}
    for index, name in enumerate(header):
        key = _header_key(name)
        for field, names in SYNONYMS.items():
            if key in names and field not in columns.values():
                columns[index] = field
                break
    fields = set(columns.values())
    missing = [label for field, label in (("company", "company"), ("role", "role")) if field not in fields]
    if missing:
        raise ImportProblem(
            "We could not find a " + " or ".join(f"“{m}”" for m in missing) + " column. Put a header row on top with at least Company and Role (Title and Position work too)."
        )
    if len(rows) - 1 > MAX_ROWS:
        raise ImportProblem(f"That file has more than {MAX_ROWS} jobs. Import it in parts.")
    data = []
    for number, row in rows[1:]:
        data.append((number, {field: (row[index].strip() if index < len(row) else "") for index, field in columns.items()}))
    return columns, data


def _row_to_values(number: int, raw: dict) -> tuple[dict | None, list[str]]:
    """The checked values for one row, or None and why it cannot be imported; plus any gentler warnings."""
    warnings: list[str] = []
    company, role = raw.get("company", ""), raw.get("role", "")
    if not company or not role:
        return None, [f"Row {number}: the {'company' if not company else 'role'} is empty."]
    if len(company) > 160 or len(role) > 200:
        return None, [f"Row {number}: the company or role is too long (160 and 200 letters at most)."]
    url = raw.get("url", "")
    if url:
        if len(url) > 600:
            return None, [f"Row {number}: the link is too long."]
        try:
            URLValidator(schemes=["http", "https"])(url)
        except ValidationError:
            return None, [f"Row {number}: “{url[:60]}” is not a web address. Use one that starts with https://, or leave it empty."]
    values: dict = {"company": company, "role": role, "url": url, "notes": raw.get("notes", "")[:10000], "location_text": raw.get("location", "")[:160]}
    for field, label in DATE_FIELDS.items():
        try:
            values[field] = parse_date(raw.get(field, ""))
        except ValueError as exc:
            return None, [f"Row {number}: the {label} “{str(exc)[:30]}” is not a date. Use 2026-10-25 or 25/10/2026 (day first)."]
    country = raw.get("country", "")
    values["country"] = ""
    if country:
        if len(country) == 2 and country.upper() in geo.COUNTRIES:
            values["country"] = country.upper()
        else:
            codes = geo.resolve_place(country)
            if codes and len(codes) == 1 and "*" not in codes:
                values["country"] = next(iter(codes))
            else:
                warnings.append(f"Row {number}: the country “{country[:30]}” was not recognised, so it was left blank.")
    status_name = raw.get("status", "")
    status = board.find_status(status_name) if status_name else None
    if status_name and status is None:
        warnings.append(f"Row {number}: there is no status called “{status_name[:30]}”, so it was saved as Saved.")
    values["status"] = status
    return values, warnings


def read_file(owner, raw: bytes, preview: bool) -> dict:
    """Check the file and, unless `preview`, add its jobs to `owner`'s tracker. Returns the report (see the module docstring); raises ImportProblem for an unusable file."""
    from tracker.services import linkedinexport  # LinkedIn's own data export (the zip, or its Saved Jobs / Job Applications CSV)

    if linkedinexport.is_zip(raw) or linkedinexport.is_linkedin_csv(raw):
        return linkedinexport.read(owner, raw, preview)
    columns, data = _table(decode(raw))
    existing = list(Application.objects.filter(owner=owner).values_list("url", "company", "role"))
    seen_urls = {u for u, _, _ in existing if u}
    seen_keys = {tracking.norm_key(c, r) for _, c, r in existing}
    room = max(0, settings.STILLOPEN_MAX_APPLICATIONS - len(existing))
    start = tracking.starting_status()

    to_add, skipped, problems, warnings = [], [], [], []
    stopped = ""
    counts = {"skipped": 0, "problems": 0}
    for number, raw_row in data:
        values, notes = _row_to_values(number, raw_row)
        if values is None:
            counts["problems"] += 1
            problems.append({"row": number, "message": notes[0]})
            continue
        warnings.extend(notes)
        key = tracking.norm_key(values["company"], values["role"])
        why = ""
        if values["url"] and values["url"] in seen_urls:
            why = "You already track a job with this link, or it is repeated in the file."
        elif key in seen_keys:
            why = "You already track this role at this company, or it is repeated in the file."
        if why:
            counts["skipped"] += 1
            skipped.append({"row": number, "company": values["company"], "role": values["role"], "reason": why})
            continue
        if len(to_add) >= room:
            stopped = f"You have reached the limit of {settings.STILLOPEN_MAX_APPLICATIONS} tracked jobs, so the import stopped at row {number}. Remove some jobs you no longer need, then import the rest."
            break
        if values["url"]:
            seen_urls.add(values["url"])
        seen_keys.add(key)
        to_add.append((number, values))

    report = {
        "preview": preview,
        "columns": sorted(set(columns.values())),
        "rows_read": len(data),
        "will_add": len(to_add),
        "skipped_count": counts["skipped"],
        "problem_count": counts["problems"],
        "skipped": skipped[:SHOWN],
        "problems": problems[:SHOWN],
        "warnings": warnings[:SHOWN],
        "stopped": stopped,
        "rows": [
            {"row": n, "company": v["company"], "role": v["role"], "link": v["url"], "status": (v["status"] or start).name}
            for n, v in to_add[:SHOWN]
        ],
    }
    if preview:
        return report
    with transaction.atomic():
        events = []
        for _, v in to_add:
            app = Application(
                owner=owner, company=v["company"], role=v["role"], url=v["url"], notes=v["notes"], location_text=v["location_text"], country=v["country"],
                status=v["status"] or start, applied_date=v["applied"], follow_up_date=v["follow_up"], deadline=v["deadline"],
                details_source="manual" if (v["location_text"] or v["country"]) else "",
            )
            if v["found"]:
                app.found_date = v["found"]
            app.save()
            events.append(Event(application=app, kind="note", text="Imported from a spreadsheet"))
        Event.objects.bulk_create(events)
    report["added"] = len(to_add)
    return report
