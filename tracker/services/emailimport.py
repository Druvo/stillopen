"""Reading the jobs in a person's OWN job-alert email (LinkedIn, Indeed, Glassdoor, Google or any list of jobs) that they pasted or saved as .eml.

Pure text work, standard library only: no network, no JavaScript, no link is ever opened. The email is data. It is read into rows
(title, company, location, link, pay), the links are cleaned (tracking removed, redirect wrappers opened as TEXT, only http and https kept,
unsubscribe and settings links dropped), and the same email always gives the same rows in the same order, so the preview and the real
import agree.
"""
import email
import re
from email import policy
from html.parser import HTMLParser

from django.conf import settings
from django.db import transaction

from tracker.models import Application, Event
from tracker.services import blockedhosts, geo, tracking

MAX_BYTES = 500 * 1024
MAX_JOBS = 100
NOTE = "Imported from an email"

_BLOCK_TAGS = {"p", "div", "br", "tr", "td", "th", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer", "center", "blockquote"}
_SKIP_TAGS = {"script", "style", "head", "title", "noscript", "svg", "template"}
_HIDDEN = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|max-height\s*:\s*0", re.I)
_VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "source", "track"}

_URL = re.compile(r"https?://[^\s<>\"'\\]+", re.I)
_MD_LINK = re.compile(r"\[([^\]\n]{1,200})\]\((https?://[^)\s]+)\)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠﻿]")

# links that are never jobs
_BAD_LINK = re.compile(
    r"unsubscribe|optout|opt-out|opt_out|/settings|/preferences|preference|privacy|/help|help\.|support\.|/terms|/legal|/policy|manage[-_]?(?:alert|notif|email|sub)|"
    r"emailpref|notification|/feedback|safety|/about|/feed|/in/|/company/|/school/|/mynetwork|/messaging|/profile|/login|/signin|/sign-in|/account|/download|"
    r"play\.google\.com|apps\.apple\.com|facebook\.com|twitter\.com|x\.com/|instagram\.com|youtube\.com|\.(?:png|jpe?g|gif|svg|webp|ico)(?:\?|$)|^mailto:|^tel:",
    re.I,
)
_JOBLIKE_PATH = re.compile(r"job|career|position|opening|vacanc|viewjob|/apply|posting|requisition|/role|/rc/clk|pagead|/jl/|listing|opportunit|hiring|recruit|gh_jid|lever\.co|ashbyhq|workable|greenhouse|smartrecruiters|myworkdayjobs|icims|bamboohr", re.I)
_GENERIC_ANCHOR = re.compile(
    r"^(?:view|see|open|apply|read|show|get|click|learn|more|details?|job|jobs|here|link|url|apply now|view job|view all|see all|easy apply|view details|"
    r"see details|see job|view this job|apply on|link to job|job link|job url|web ?address)\b[\s:.\-–—>»]*(?:job|jobs|details?|more|now|here|all|all jobs|this job|on \w+|link|url)?[\s:.>»]*$",
    re.I,
)
_NOISE = re.compile(
    r"^(?:view(?: job| all| jobs| details)?|see (?:all|more|job|details)|apply(?: now| on .+)?|easy apply|unsubscribe|manage (?:your )?(?:job )?alerts?|edit (?:your )?alert|"
    r"promoted|actively (?:recruiting|hiring)|be an early applicant|new(?=\s*$)|top pick|recommended|sponsored|\d+ (?:school alumni|connections?|applicants?|people|new jobs?)|"
    r"you are receiving|this email was|this message was|sent to|©|copyright|privacy|terms|help center|learn why|why am i|to stop receiving|if you no longer|"
    r"your job alert|job alert for|jobs? (?:for|matching|similar|you may|in)|new jobs? (?:for|in|matching)|recommended jobs|jobs similar|more jobs|similar jobs|here are|"
    r"hi\b|hello\b|dear\b|thanks|thank you|regards|forwarded message|from:|to:|date:|subject:|sent:|cc:|-{2,}|_{2,}|={2,}|—{2,}|view in browser|view this email|open in browser|"
    r"download the app|get the app|follow us|\w+ is a registered|all rights reserved|posted \d|\d+ (?:hours?|days?|weeks?|minutes?) ago|just now|today|yesterday|"
    r"reposted|verified|be one of the first|apply with|quick apply|save|share|report this|not interested|dismiss|read more)\b",
    re.I,
)
_SALARY = re.compile(
    r"(?:[$€£₹]|\b(?:USD|EUR|GBP|MYR|AED|SGD|BDT|CAD|AUD|INR|RM|Rs\.?|SAR|QAR)\b)\s?\d[\d,.]*\s*[kKmM]?"
    r"(?:\s*(?:-|–|—|to)\s*(?:[$€£₹]|\b(?:USD|EUR|GBP|MYR|AED|SGD|BDT|CAD|AUD|INR|RM|Rs\.?|SAR|QAR)\b)?\s?\d[\d,.]*\s*[kKmM]?)?"
    r"(?:\s*(?:a|an|per|/|each)\s*(?:year|yr|month|mo|hour|hr|annum|week|day|yearly|monthly|hourly))?",
    re.I,
)
_SPLIT = re.compile(r"\s+[·•|]\s+|\s+[-–—]\s+")
_AT_COMPANY = re.compile(r"^(?P<title>.{3,}?)\s+(?:at|@)\s+(?P<company>[^,|·•]{2,80})$")
_VERIFIED = re.compile(r"\s*(?:\(with verification\)|with verification)\s*$", re.I)


class EmailProblem(Exception):
    """The input is unusable as a whole; the message is in plain words."""


# ---- turning the email into lines ---------------------------------------------------------------------------------

class _Lines(HTMLParser):
    """HTML to lines of text. Each line is {"text", "links": [(href, anchor text)]}; an empty line (text "") is a gap between blocks.
    Scripts, styles and hidden text are dropped; nothing runs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[dict] = []
        self._text: list[str] = []
        self._links: list[tuple[str, str]] = []
        self._skip = 0
        self._hidden: list[str] = []  # open tags of a hidden block, to know when it closes
        self._href = None
        self._anchor: list[str] = []
        self._br_run = 0

    def _flush(self, gap: bool = False):
        text = re.sub(r"\s+", " ", "".join(self._text)).strip()
        if text or self._links:
            self.lines.append({"text": text, "links": self._links})
            self._br_run = 0
        elif gap and self.lines and self.lines[-1]["text"] != "":
            self.lines.append({"text": "", "links": []})
        self._text, self._links = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._skip or self._hidden:
            if tag not in _VOID:
                if tag in _SKIP_TAGS:
                    self._skip += 1
                elif self._hidden:
                    self._hidden.append(tag)
            return
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if _HIDDEN.search(a.get("style") or "") or a.get("hidden") is not None:
            if tag not in _VOID:
                self._hidden.append(tag)
            return
        if tag == "br":
            self._br_run += 1
            self._flush(gap=self._br_run >= 2)
            return
        if tag == "hr":
            self._flush(gap=True)
            return
        if tag in _BLOCK_TAGS:
            self._flush()
        if tag == "a":
            self._href = (a.get("href") or "").strip()
            self._anchor = []

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
            return
        if self._hidden:
            if tag not in _VOID:
                self._hidden.pop()
            return
        if tag == "a" and self._href is not None:
            anchor = re.sub(r"\s+", " ", "".join(self._anchor)).strip()
            if self._href:
                self._links.append((self._href, anchor))
            self._href = None
        if tag in _BLOCK_TAGS:
            self._flush(gap=tag in ("table", "ul", "ol"))

    def handle_data(self, data):
        if self._skip or self._hidden:
            return
        self._text.append(data)
        if self._href is not None:
            self._anchor.append(data)

    def close(self):
        super().close()
        self._flush()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", _CONTROL.sub("", text or "")).strip()


def _html_lines(source: str) -> list[dict]:
    parser = _Lines()
    try:
        parser.feed(source)
        parser.close()
    except Exception:  # the parser is lenient; a truly broken page just gives what was read so far
        parser._flush()
    return parser.lines


def _text_lines(source: str) -> list[dict]:
    lines = []
    for raw in source.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        raw = _CONTROL.sub("", raw).strip()
        raw = re.sub(r"^[>\s]+", "", raw)  # quoted forward markers
        if not raw:
            if lines and lines[-1]["text"] != "":
                lines.append({"text": "", "links": []})
            continue
        links = []

        def md(m):
            links.append((m.group(2), m.group(1).strip()))
            return m.group(1)

        raw = _MD_LINK.sub(md, raw)
        leftover = raw
        found = []
        for m in _URL.finditer(raw):
            url = m.group(0).rstrip(".,;:!?)]}>'\"")
            found.append(url)
        for url in found:
            leftover = leftover.replace(url, " ")
        leftover = _clean_text(leftover.replace("<>", " ").replace("()", " ").replace("[]", " "))
        for url in found:
            links.append((url, leftover if len(found) == 1 else ""))
        text = leftover if found else _clean_text(raw)
        lines.append({"text": text, "links": links, "_url_only": bool(found) and not leftover})
    return lines


def _looks_html(text: str) -> bool:
    return bool(re.search(r"<(?:a|table|div|p|br|html|body|td|span)\b[^>]*>", text, re.I))


def _from_eml(raw: bytes) -> tuple[str, str]:
    try:
        message = email.message_from_bytes(raw, policy=policy.default)
    except Exception:
        raise EmailProblem("We could not read that file as an email. Save the message again as .eml, or paste its text instead.") from None
    plain, html = [], []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        kind = part.get_content_type()
        if kind not in ("text/plain", "text/html"):
            continue
        try:
            body = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            body = payload.decode("utf-8", "replace")
        if not isinstance(body, str):
            continue
        (html if kind == "text/html" else plain).append(body)
    subject = str(message.get("subject") or "")
    return "\n".join(plain), "\n".join(html), subject


# ---- reading jobs out of lines ---------------------------------------------------------------------------------------

def _is_noise(text: str) -> bool:
    return bool(_NOISE.match(text)) or bool(_GENERIC_ANCHOR.match(text))


def _job_like(href: str, url: str, anchor_given: bool) -> bool:
    if not url or _BAD_LINK.search(url) or _BAD_LINK.search(href):
        return False
    site = blockedhosts.blocked_site(url)
    if site == "linkedin":
        return bool(blockedhosts.canonical_linkedin(url))
    if site == "indeed":
        return bool(re.search(r"viewjob|/rc/clk|/pagead|/job/|jk=|/m/", url))
    if site == "glassdoor":
        return bool(re.search(r"job-listing|joblisting|partner|/job/|jl=", url, re.I))
    return bool(_JOBLIKE_PATH.search(url)) or not anchor_given


def _info_line(text: str) -> bool:
    return 1 < len(text) <= 160 and not _is_noise(text) and not _URL.search(text)


def _split_parts(text: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(text) if p.strip()]


def _salary_of(text: str) -> str:
    m = _SALARY.search(text)
    if not m:
        return ""
    value = m.group(0).strip()
    return value if re.search(r"\d{2,}", value) else ""


def _fill(row: dict, info: list[str]):
    """Company, location and pay from the lines that belong to one job, in the order they appear."""
    rest = []
    for line in info:
        pay = _salary_of(line)
        if pay and not row["salary"] and len(line) <= 90 and (len(pay) >= len(line) * 0.4 or re.search(r"a year|per year|/yr|a month|per month|an hour|per hour|salary|pay", line, re.I)):
            row["salary"] = pay
        else:
            rest.append(line)
    if not rest:
        return
    parts = _split_parts(rest[0])
    if len(parts) >= 2:
        row["company"], row["location"] = parts[0], parts[1]
        if len(parts) > 2 and not row["salary"] and _salary_of(parts[2]):
            row["salary"] = _salary_of(parts[2])
        return
    row["company"] = rest[0]
    if len(rest) > 1:
        loc = _split_parts(rest[1])
        row["location"] = loc[0] if loc else rest[1]


def _gather_before(lines: list[dict], index: int, limit: int = 3) -> list[str]:
    out = []
    i = index - 1
    while i >= 0 and len(out) < limit:
        line = lines[i]
        if line["text"] == "" and not line["links"]:
            break
        if line["links"] and any(_job_like(h, blockedhosts.clean_link(h), True) for h, _ in line["links"]) and line["text"] and not line.get("_url_only"):
            break
        if line.get("_url_only") and line["links"]:
            break
        if _info_line(line["text"]):
            out.append(line["text"])
        i -= 1
    return list(reversed(out))


def _gather_after(lines: list[dict], index: int, limit: int = 3) -> list[str]:
    out = []
    i = index + 1
    while i < len(lines) and len(out) < limit:
        line = lines[i]
        if line["text"] == "" and not line["links"]:
            break
        if line["links"] and any(_job_like(h, blockedhosts.clean_link(h), True) for h, _ in line["links"]):
            if not line["text"] or _GENERIC_ANCHOR.match(line["text"]) or _NOISE.match(line["text"]):
                i += 1
                continue
            break
        if _info_line(line["text"]):
            out.append(line["text"])
        i += 1
    return out


def _tidy(value: str, limit: int) -> str:
    return _clean_text(value)[:limit]


def _finish(row: dict) -> dict:
    row["title"] = _tidy(_VERIFIED.sub("", row["title"]), 200)
    if not row["company"]:
        found = _AT_COMPANY.match(row["title"])
        if found:
            row["title"], row["company"] = _tidy(found.group("title"), 200), found.group("company")
    row["company"] = _tidy(row["company"], 160)
    row["location"] = _tidy(row["location"], 160)
    row["salary"] = _tidy(row["salary"], 160)
    return row


def _rows_from_links(lines: list[dict]) -> list[dict]:
    items = []
    for index, line in enumerate(lines):
        for href, anchor in line["links"]:
            url = blockedhosts.clean_link(href)
            anchor = _clean_text(anchor).rstrip(" :-–—")
            if not _job_like(href, url, bool(anchor) or bool(line["text"])):
                continue
            generic = not anchor or _is_noise(anchor) or bool(_URL.search(anchor)) or len(anchor) > 150
            items.append((index, url, anchor, generic))
    rows: dict[str, tuple[int, dict]] = {}
    # links whose own words are the job title first; a "View job" or logo link only for jobs nothing else described
    for generic_pass in (False, True):
        for index, url, anchor, generic in items:
            if generic is not generic_pass or (url in rows):
                continue
            row = {"title": "", "company": "", "location": "", "salary": "", "url": url}
            if not generic:
                row["title"] = anchor
                _fill(row, _gather_after(lines, index))
            else:
                before = _gather_before(lines, index)
                if not before:
                    continue
                row["title"] = before[0]
                _fill(row, before[1:])
            if not row["title"] or _is_noise(row["title"]):
                continue
            rows[url] = (index, _finish(row))
    return [row for _, row in sorted(rows.values(), key=lambda pair: pair[0])]


_TERMINATOR = re.compile(
    r"^(?:promoted|easy apply|actively (?:recruiting|hiring)|be an early applicant|(?:over )?\d+\+? (?:applicants?|clicks?|people clicked)|"
    r"(?:posted |reposted )?(?:\d+ )?(?:minutes?|hours?|days?|weeks?|months?) ago|just now|viewed)\b",
    re.I,
)
_NOTIFICATION = re.compile(
    r"^(?:new jobs?(?: for you)?|job alert|new job alert|recommended job|jobs? for you|top job pick)\s*[:\-–—]\s*(?P<title>.{3,}?)\s+at\s+(?P<company>[^,|·•]{2,80}?)\.?$",
    re.I,
)
LINKEDIN_SEARCH = "https://www.linkedin.com/jobs/search/?keywords={}"


def linkedin_search_link(title: str, company: str) -> str:
    """A link the person clicks themselves to find the job again on LinkedIn. Built from text; nothing is fetched."""
    from urllib.parse import quote_plus

    return LINKEDIN_SEARCH.format(quote_plus(f"{title} {company}".strip()))


def _same_line(a: str, b: str) -> bool:
    norm = lambda t: re.sub(r"\s*(?:\(with verification\)|with verification)$", "", t.strip().lower())  # noqa: E731
    return norm(a) == norm(b)


def _rows_from_visible_text(lines: list[dict]) -> list[dict]:
    """Text copied by hand from LinkedIn's notifications or results page (or a rich-text paste of an email): blocks of title, company, place and
    noise like "Promoted" or "3 applicants", with no links. A block ends at a blank line or at a noise line such as "Easy Apply" or "2 days ago";
    "New jobs for you: Title at Company" sentences are read too."""
    rows, current = [], []

    def close():
        nonlocal current
        block = current
        current = []
        if 2 <= len(block) <= 6 and not any(len(x) > 110 or x.endswith((".", "!", "?")) for x in block[:3]):
            row = {"title": block[0], "company": "", "location": "", "salary": "", "url": ""}
            _fill(row, block[1:4])
            rows.append(_finish(row))

    for line in lines:
        text = line["text"]
        if text == "":
            close()
            continue
        found = _NOTIFICATION.match(text)
        if found:
            close()
            rows.append(_finish({"title": found.group("title"), "company": found.group("company"), "location": "", "salary": "", "url": ""}))
            continue
        if _TERMINATOR.match(text):
            close()
            continue
        if _info_line(text) and not (current and _same_line(current[-1], text)):
            current.append(text)
    close()
    seen, unique = set(), []
    for row in rows:
        key = (row["title"].lower(), row["company"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def read(text: str = "", html: str = "", eml: bytes | None = None) -> dict:
    """The jobs in one email: {"rows": [...], "problems": [...]}; raises EmailProblem for empty or unusable input. Never touches the network."""
    subject = ""
    if eml is not None:
        if len(eml) > MAX_BYTES:
            raise EmailProblem("That email is bigger than 500 KB. Paste just the part with the jobs.")
        text, html, subject = _from_eml(eml)
    if len((text or "").encode("utf-8", "ignore")) + len((html or "").encode("utf-8", "ignore")) > MAX_BYTES:
        raise EmailProblem("That is bigger than 500 KB. Paste just the part of the email with the jobs.")
    if not (text or "").strip() and not (html or "").strip():
        raise EmailProblem("Paste the email first, or choose an .eml file.")
    problems: list[str] = []
    if (html or "").strip():
        lines = _html_lines(html)
    elif _looks_html(text):
        lines = _html_lines(text)
    else:
        lines = _text_lines(text)
    rows = _rows_from_links(lines)
    linked = bool(rows)
    if not rows:
        rows = _rows_from_visible_text(lines)
        if rows:
            problems.append("This text has no links, so these jobs are saved without one, with a LinkedIn search link in the notes. If it came from an email, save the email as an .eml file and choose that instead to keep the real links.")
    if not rows:
        problems.append("We could not find any jobs in that email. Paste the whole email (not only a part), or choose it as an .eml file.")
    if len(rows) > MAX_JOBS:
        problems.append(f"That email lists more than {MAX_JOBS} jobs, so only the first {MAX_JOBS} are shown.")
        rows = rows[:MAX_JOBS]
    for number, row in enumerate(rows):
        row["index"] = number
        row["problems"] = []
        if not row["company"]:
            row["problems"].append("We could not find the company. It will be saved as “Company not stated”; you can edit it afterwards.")
        if not row["url"]:
            row["problems"].append("No link: you will need to open it on LinkedIn to apply.")
    return {"rows": rows, "problems": problems, "subject": _tidy(subject, 200)}


# ---- adding ----------------------------------------------------------------------------------------------------------

def _company(row: dict) -> str:
    return row["company"] or "Company not stated"


def _duplicate(owner, row: dict):
    return tracking.find_duplicate(owner, _company(row) if row["company"] else "", row["title"], row["url"])


def check(owner, found: dict) -> dict:
    """The preview: each row, whether the person already tracks it, and what the real call would do."""
    rows = []
    will_add = 0
    seen_keys: set[str] = set()
    for row in found["rows"]:
        same = _duplicate(owner, row)
        key = tracking.norm_key(_company(row), row["title"])
        repeated = key in seen_keys and not same
        seen_keys.add(key)
        out = {k: row[k] for k in ("index", "title", "company", "location", "salary", "url", "problems")}
        out["duplicate"] = tracking.duplicate_info(same) if same else None
        out["importable"] = not same and not repeated
        if repeated:
            out["problems"] = [*out["problems"], "The same job appears twice in this email."]
        will_add += out["importable"]
        rows.append(out)
    return {"preview": True, "found": len(rows), "will_add": will_add, "rows": rows, "problems": found["problems"]}


def add(owner, found: dict, selected: list[int] | None) -> dict:
    """Add the chosen rows (all of them when `selected` is None) as Saved jobs. Duplicates are skipped and counted; the job limit stops the import."""
    by_index = {r["index"]: r for r in found["rows"]}
    chosen = [by_index[i] for i in (selected if selected is not None else sorted(by_index)) if i in by_index]
    chosen = list({r["index"]: r for r in chosen}.values())
    added = 0
    skipped: list[dict] = []
    stopped = ""
    status = tracking.starting_status()
    with transaction.atomic():
        for row in chosen:
            if tracking.at_job_limit(owner):
                stopped = tracking.job_limit_message()
                break
            same = _duplicate(owner, row)
            if same:
                skipped.append({"title": row["title"], "company": _company(row), "reason": tracking.duplicate_message(same)})
                continue
            app = Application(
                owner=owner, company=_company(row), role=row["title"], url=row["url"], location_text=row["location"], advertised_pay=row["salary"],
                status=status,
                notes=f"Find it on LinkedIn: {linkedin_search_link(row['title'], row['company'])}" if not row["url"] else "",
            )
            detected = geo.detect(row["title"], row["location"])
            if row["location"]:
                detected.pop("location_text", None)
            for name in ("country", "arrangement", "employment_type", "seniority", "location_text"):
                if detected.get(name) and not getattr(app, name):
                    setattr(app, name, detected[name])
            if detected:
                app.details_source = "detected"
            app.save()
            Event.objects.create(application=app, kind="note", text=NOTE)
            added += 1
    return {"preview": False, "added": added, "skipped_count": len(skipped), "skipped": skipped[:50], "stopped": stopped, "found": len(found["rows"]), "problems": found["problems"]}


def hourly_limit() -> int:
    return getattr(settings, "STILLOPEN_IMPORTS_PER_HOUR", 30)
