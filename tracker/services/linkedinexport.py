"""Bringing in the person's OWN LinkedIn data export: "Saved Jobs.csv" and "Job Applications.csv", or the whole export .zip.

LinkedIn lets every member download a copy of their data. This module reads only those two kinds of file, in memory (nothing is extracted
to disk, no other file in the zip is opened), and never opens a link. Saved jobs come in as Saved; sent applications come in as Applied with
their date. Contact email, phone number, résumé name and the question-and-answer text are in LinkedIn's file but are never read into
anything: only company, job title, link and date are used.

Zip safety: the zip is capped, every entry name is checked (no absolute paths, no `..`, no backslashes), the entry count, each entry's
declared size, its compression ratio and the bytes actually read are limited, and a zip whose declared and real sizes disagree is refused.
"""
import csv
import io
import re
import zipfile
from datetime import date

from django.conf import settings
from django.db import transaction

from tracker.models import Application, Event
from tracker.services import blockedhosts, board, tracking
from tracker.services.jobimport import ImportProblem

MAX_ZIP = 25 * 1024 * 1024
MAX_ENTRY = 5 * 1024 * 1024
MAX_MEMBERS = 3000
MAX_RATIO = 200  # declared size over compressed size; real CSVs compress far less than this
MAX_ROWS = 2000  # per file
SHOWN = 50
SOURCE_NOTE = "Imported from your LinkedIn data"

_WANTED = re.compile(r"^(?:[^/]+/){0,2}(saved jobs|job applications)(?:[ _\-(][^/]*)?\.csv$", re.I)
_COLUMNS = {
    "url": {"job url", "job link", "url", "link", "job posting url", "posting url"},
    "title": {"job title", "title", "position", "role"},
    "company": {"company name", "company", "employer"},
    "date": {"saved date", "application date", "date applied", "date saved", "date"},
}
KIND_LABEL = {"saved": "Saved Jobs", "applied": "Job Applications"}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def is_zip(raw: bytes) -> bool:
    return raw[:4] in (b"PK\x03\x04", b"PK\x05\x06")


def _decode(raw: bytes) -> str:
    if b"\x00" in raw[:4096]:
        raise ImportProblem("That does not look like a CSV file from LinkedIn.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportProblem("We could not read the letters in that file.")


def _kind_of(header: list[str]) -> str:
    keys = {_key(h) for h in header}
    if "job url" not in keys and "job link" not in keys:
        return ""
    if "application date" in keys or "date applied" in keys:
        return "applied"
    if "saved date" in keys or "date saved" in keys:
        return "saved"
    return ""


def is_linkedin_csv(raw: bytes) -> bool:
    try:
        first = next((line for line in raw[:8192].decode("utf-8-sig", "replace").splitlines() if line.strip()), "")
        return bool(_kind_of(next(csv.reader([first]), [])))
    except (csv.Error, StopIteration):
        return False


def parse_date(text: str) -> date | None:
    """LinkedIn writes "2025-10-22 21:14:03 UTC" or "10/22/25, 9:14 PM". The second is month first unless the first number cannot be a month."""
    text = (text or "").strip()
    if not text:
        return None
    iso = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    us = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2}|\d{4})\b", text)
    try:
        if iso:
            return date(int(iso[1]), int(iso[2]), int(iso[3]))
        if us:
            a, b, y = int(us[1]), int(us[2]), int(us[3])
            y += 2000 if y < 100 else 0
            month, day = (a, b) if a <= 12 else (b, a)
            return date(y, month, day)
    except ValueError:
        pass
    return None


def _rows(text: str, kind: str) -> tuple[list[tuple[int, dict]], int]:
    """(readable rows as (row number, fields), unreadable count) of one file. Only the four wanted columns are ever looked at."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next((r for r in reader if any(c.strip() for c in r)))
    except StopIteration:
        return [], 0
    index = {}
    for position, name in enumerate(header):
        k = _key(name)
        for field, names in _COLUMNS.items():
            if k in names and field not in index:
                index[field] = position
    out, bad = [], 0
    for number, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        if len(out) + bad >= MAX_ROWS:
            break
        cell = lambda f: (row[index[f]].strip() if f in index and index[f] < len(row) else "")  # noqa: E731
        company, title, link = cell("company"), cell("title"), cell("url")
        if not company or not title or len(company) > 160 or len(title) > 200:
            bad += 1
            continue
        url = ""
        if link:
            url = blockedhosts.clean_link(link)
            if not url:
                bad += 1
                continue
        out.append((number, {"company": company, "title": title, "url": url, "date": parse_date(cell("date"))}))
    return out, bad


def _entries(raw: bytes) -> tuple[list[tuple[str, str, bytes]], int]:
    """[(entry name, kind, bytes)] of the wanted files in a zip, and how many other entries were ignored. Refuses anything unsafe."""
    if len(raw) > MAX_ZIP:
        raise ImportProblem("That file is bigger than 25 MB. Request only the Jobs part of your data from LinkedIn, or choose just the two CSV files from the zip.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError):
        raise ImportProblem("We could not open that zip file. Download it from LinkedIn again, or choose the two CSV files from it.") from None
    if len(infos) > MAX_MEMBERS:
        raise ImportProblem("That zip has too many files to be a normal LinkedIn export, so we did not open it.")
    for info in infos:
        name = info.filename
        parts = name.replace("\\", "/").split("/")
        if "\\" in name or name.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", name) or "\x00" in name:
            raise ImportProblem("That zip has file names we do not trust, so we did not open it.")
    wanted, ignored = [], 0
    for info in infos:
        match = _WANTED.match(info.filename)
        if info.is_dir() or not match:
            ignored += 1
            continue
        if info.flag_bits & 0x1:
            raise ImportProblem("That zip is password protected. Download the data from LinkedIn again; their zip has no password.")
        if info.file_size > MAX_ENTRY or (info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_RATIO and info.file_size > 100_000):
            raise ImportProblem("One of the files in that zip is far bigger than a LinkedIn jobs file should be, so we did not open it.")
        try:
            with archive.open(info) as handle:
                data = handle.read(MAX_ENTRY + 1)
        except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError, EOFError, ValueError):
            raise ImportProblem("We could not read a file inside that zip. Download it from LinkedIn again.") from None
        if len(data) > MAX_ENTRY or len(data) != info.file_size:
            raise ImportProblem("A file in that zip is not the size it says it is, so we did not open it.")
        kind = "saved" if match.group(1).lower() == "saved jobs" else "applied"
        wanted.append((info.filename.rsplit("/", 1)[-1], kind, data))
    return wanted, ignored


def read(owner, raw: bytes, preview: bool) -> dict:
    """Check a LinkedIn export (the zip, or one of its CSVs) and, unless `preview`, add its jobs. See the module note for what is and is not read."""
    if is_zip(raw):
        files, ignored = _entries(raw)
        if not files:
            raise ImportProblem(
                "We could not find “Saved Jobs.csv” or “Job Applications.csv” in that zip. When you ask LinkedIn for your data, tick Jobs (or everything), then choose the file they send."
            )
    else:
        if len(raw) > MAX_ENTRY:
            raise ImportProblem("That file is bigger than 5 MB.")
        text = _decode(raw)
        header = next(csv.reader(io.StringIO(text.lstrip("﻿"))), [])
        kind = _kind_of(header)
        if not kind:
            raise ImportProblem("That does not look like “Saved Jobs.csv” or “Job Applications.csv” from LinkedIn.")
        files, ignored = [("Saved Jobs.csv" if kind == "saved" else "Job Applications.csv", kind, raw)], 0
    files.sort(key=lambda f: 0 if f[1] == "applied" else 1)  # a job that is both saved and applied counts as applied

    existing = list(Application.objects.filter(owner=owner).values_list("url", "company", "role"))
    seen_urls = {blockedhosts.clean_link(u) or u for u, _, _ in existing if u}
    seen_keys = {tracking.norm_key(c, r) for _, c, r in existing}
    room = max(0, settings.STILLOPEN_MAX_APPLICATIONS - len(existing))

    summaries, to_add, skipped, problems = [], [], [], []
    stopped = ""
    for name, kind, data in files:
        rows, bad = _rows(_decode(data), kind)
        new = dup = 0
        for number, fields in rows:
            why = ""
            if fields["url"] and fields["url"] in seen_urls:
                why = "You already track a job with this link."
            elif tracking.norm_key(fields["company"], fields["title"]) in seen_keys:
                why = "You already track this role at this company."
            if why:
                dup += 1
                skipped.append({"row": number, "file": name, "company": fields["company"], "role": fields["title"], "reason": why})
                continue
            if len(to_add) >= room:
                stopped = tracking.job_limit_message()
                break
            if fields["url"]:
                seen_urls.add(fields["url"])
            seen_keys.add(tracking.norm_key(fields["company"], fields["title"]))
            to_add.append((name, kind, number, fields))
            new += 1
        if bad:
            problems.append({"row": 0, "file": name, "message": f"{name}: {bad} row{'s' if bad != 1 else ''} could not be read (a missing company or job title, or a link that is not a web address)."})
        summaries.append({"name": name, "kind": kind, "label": KIND_LABEL[kind], "found": len(rows) + bad, "new": new, "duplicates": dup, "unreadable": bad})
        if stopped:
            break

    saved_status = board.find_status("Saved") or tracking.starting_status()
    applied_status = board.find_status("Applied") or saved_status
    report = {
        "preview": preview,
        "source": "linkedin",
        "columns": ["company", "role", "link", "date"],
        "rows_read": sum(s["found"] for s in summaries),
        "will_add": len(to_add),
        "skipped_count": len(skipped),
        "problem_count": sum(s["unreadable"] for s in summaries),
        "skipped": skipped[:SHOWN],
        "problems": problems[:SHOWN],
        "warnings": [],
        "stopped": stopped,
        "files": summaries,
        "ignored_files": ignored,
        "privacy": "Contact details, phone numbers, résumé names and application answers in LinkedIn's file are never read or kept.",
        "rows": [
            {"row": n, "file": name, "company": f["company"], "role": f["title"], "link": f["url"], "status": (applied_status if kind == "applied" else saved_status).name}
            for name, kind, n, f in to_add[:SHOWN]
        ],
    }
    if preview:
        return report
    with transaction.atomic():
        events = []
        for _, kind, _, f in to_add:
            applied = kind == "applied"
            when = f["date"]
            app = Application(
                owner=owner, company=f["company"], role=f["title"], url=f["url"], status=applied_status if applied else saved_status,
                applied_date=when if applied else None, applied_channel="linkedin" if applied else "",
            )
            if when:
                app.found_date = when
            app.save()
            if applied:
                text = f"{SOURCE_NOTE} (application sent {when.isoformat()})" if when else f"{SOURCE_NOTE} (application sent, date not given)"
            else:
                text = f"{SOURCE_NOTE} (saved{' on ' + when.isoformat() if when else ''})"
            events.append(Event(application=app, kind="note", text=text))
        Event.objects.bulk_create(events)
    report["added"] = len(to_add)
    return report
