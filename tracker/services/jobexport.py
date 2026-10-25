"""The person's jobs as a spreadsheet file (CSV that opens in Excel, Numbers and Google Sheets).

A cell that starts with = + - @ or a tab or carriage return would be run as a formula by a spreadsheet, so those get a leading apostrophe:
a job called "=HYPERLINK(...)" shows up as plain text. Everything is for one owner."""
import csv
import io

from tracker.models import Application, SiteConfig

HEADERS = [
    "Company", "Role", "Link", "Status", "Found", "Applied", "Follow up", "Deadline", "Location", "Country", "Match %", "Notes",
]

DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """The cell as text that a spreadsheet will not treat as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(DANGEROUS_START) else text


def _day(value) -> str:
    return value.isoformat() if value else ""


def rows(owner):
    """One list per job, newest first, in the order of `HEADERS`."""
    config = SiteConfig.for_user(owner)
    apps = Application.objects.filter(owner=owner).select_related("status").order_by("-found_date", "-id")
    for app in apps:
        percent = app.match_percent(config.score_scale)
        yield [
            app.company, app.role, app.url, app.status.name, _day(app.found_date), _day(app.applied_date), _day(app.follow_up_date),
            _day(app.deadline), app.location_text, app.country, "" if percent is None else percent, app.notes,
        ]


def to_csv(owner) -> str:
    """The whole file as text, with a byte-order mark so Excel reads the accents and non-Latin letters right."""
    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(HEADERS)
    for row in rows(owner):
        writer.writerow([safe_cell(cell) for cell in row])
    return out.getvalue()
