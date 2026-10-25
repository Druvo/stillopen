"""A free, rule-based "ATS check" of a CV written in Markdown.

Applicant tracking systems read a CV as plain text in a fixed order: contact details, then sections, then dated entries and bullets. This
module checks the things parsers commonly need and says so in plain words. It is a checklist, not a score from any real ATS, and it never
suggests adding something the person has not done (keyword coverage separates "your own material has it" from "not in your material").

Pure Python, deterministic, no network. Checks that cannot be judged (for example verb checks on a CV that is not in English) are left out
of the list and of the score instead of being guessed; `notes` says which.
"""
import math
import re
from collections import Counter
from datetime import date

from tracker.services.text import terms

ENGINE = 1  # bump when a check or weight changes, so remembered numbers are not shown for the old rules

CAVEAT = (
    "This is a checklist of what parsers commonly need, not a score from any real applicant tracking system, and it is not a promise "
    "about any employer's software."
)

# What our own DOCX and print page produce (see services/cvexport.py and templates/tracker/cv_print.html). True by construction.
EXPORT = {
    "single_column": True, "text_based": True, "standard_font": "Calibri", "tables": False, "images": False, "text_boxes": False,
    "headers_and_footers": False, "links_written_out": True,
    "summary": (
        "The DOCX and the print page StillOpen makes are one column of real text in Calibri, with real headings and bullets. They have no "
        "tables, images, text boxes, headers or footers, and a link is written out as its full address, so a parser reads them in order."
    ),
}

# --- vocabulary --------------------------------------------------------------------------------------------------------------------
STANDARD = {
    "summary": {"summary", "profile", "professional summary", "career summary", "personal statement", "objective", "career objective", "professional profile", "executive summary"},
    "experience": {"experience", "work experience", "work history", "professional experience", "employment history", "employment", "career history", "relevant experience"},
    "education": {"education", "education and training", "academic background", "qualifications", "academic qualifications", "education and qualifications"},
    "skills": {"skills", "technical skills", "core skills", "key skills", "core competencies", "competencies", "skills and tools", "technologies", "skills and technologies", "technical proficiencies"},
}
STANDARD_NAME = {"summary": "Summary", "experience": "Work experience", "education": "Education", "skills": "Skills"}
KNOWN_OTHER = {
    "projects", "personal projects", "selected projects", "key projects", "certifications", "certificates", "licenses and certifications", "licences and certifications",
    "languages", "awards", "honors", "honours", "awards and honors", "publications", "volunteer", "volunteering", "volunteer experience", "interests", "hobbies",
    "references", "courses", "training", "achievements", "key achievements", "activities", "additional information", "open source", "links", "contact",
    "contact details", "contact information", "professional development", "leadership", "research", "extracurricular activities",
}
_FLAT = {name: key for key, names in STANDARD.items() for name in names}
_HINTS = [
    (("journey", "story", "career", "path", "where i", "worked", "jobs", "roles"), "experience"),
    (("toolbox", "superpower", "know", "stack", "tech", "tools", "what i can", "strengths"), "skills"),
    (("about", "who i", "intro", "hello", "me"), "summary"),
    (("school", "learn", "stud", "degree", "academic", "university"), "education"),
]

VERBS = set(
    """achieved administered analysed analyzed architected assembled assisted audited authored automated built calculated captured championed
    chaired coached collaborated compiled completed configured consolidated constructed consulted coordinated created cut debugged decreased
    defined delivered deployed designed developed devised diagnosed directed documented doubled drafted drove earned edited enabled engineered
    established evaluated executed expanded facilitated finalised finalized forecast formulated founded generated grew guided halved handled
    headed identified implemented improved increased influenced initiated installed integrated introduced investigated launched led leveraged
    maintained managed mapped mentored migrated modelled modeled monitored negotiated onboarded operated optimised optimized orchestrated
    organised organized oversaw owned partnered performed piloted planned prepared presented prioritised prioritized processed produced
    programmed promoted proposed prototyped provided published raised rebuilt recruited redesigned reduced refactored refined released
    remodelled replaced reported researched resolved restructured reviewed revised rewrote saved scaled scheduled secured selected served
    shipped simplified solved sourced spearheaded standardised standardized streamlined strengthened supervised supported surveyed taught
    tested tracked trained transformed translated tripled troubleshot upgraded validated wrote won
    build create design develop deliver lead manage run write ship own drive improve reduce increase""".split()
)
_WEAK_START = re.compile(
    r"^(responsible for|duties (?:included|include)|tasked with|in charge of|worked on|worked with|helped|assisted|was|were|i\b|my\b|various|many|"
    r"experience (?:in|with)|involved in|participated in|part of)",
    re.I,
)
_PASSIVE = re.compile(
    r"\b(responsible for|duties included|duties include|involved in|was involved|were involved|participated in|assisted with|helped with|helped to|"
    r"worked on|tasked with|in charge of|various tasks)\b",
    re.I,
)
_FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'll|my|me|myself)\b")
_ENGLISH_COMMON = {"the", "and", "of", "to", "for", "with", "on", "by", "as", "from", "is", "that", "in", "a"}
# Very common words of other languages that CVs are written in. A CV is treated as not English only when these clearly outnumber the English ones.
_FOREIGN_COMMON = {
    "der", "die", "das", "und", "mit", "für", "von", "dem", "den", "des", "ist", "zu", "im", "auf", "el", "la", "los", "las", "y", "con", "para", "por", "del", "una",
    "le", "les", "du", "et", "pour", "avec", "dans", "une", "um", "uma", "com", "não", "são", "os", "as", "em", "na", "no", "che", "di", "il", "della", "per", "ve", "bir", "ile",
}
_SOFT = {
    "communication", "teamwork", "leadership", "problem solving", "time management", "adaptability", "creativity", "critical thinking",
    "work ethic", "attention to detail", "collaboration", "organisation", "organization", "flexibility", "multitasking",
}
ACRONYMS = {
    "SEO": r"search engine optimi[sz]ation", "CRM": r"customer relationship management", "ERP": r"enterprise resource planning",
    "KPI": r"key performance indicator", "ROI": r"return on investment", "SaaS": r"software as a service", "QA": r"quality assurance",
    "ETL": r"extract,? transform", "CMS": r"content management system", "SLA": r"service level agreement",
    "B2B": r"business[- ]to[- ]business", "CI/CD": r"continuous integration", "SDK": r"software development kit", "UX": r"user experience",
    "NLP": r"natural language processing", "OKR": r"objectives? and key results", "P&L": r"profit and loss", "AWS": r"amazon web services",
    "GCP": r"google cloud", "IoT": r"internet of things", "HRIS": r"human resources? information system", "PMO": r"project management office",
}
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "buff.ly", "is.gd", "rebrand.ly")
_GENERIC_LINK = {"here", "link", "click here", "this", "website", "site", "my website", "url", "this link", "click"}

# --- dates --------------------------------------------------------------------------------------------------------------------------
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_D = rf"(?:{_MON}\s+\d{{4}}|\d{{1,2}}[/.]\d{{4}}|\d{{4}}-(?:0[1-9]|1[0-2])(?!\d)|\d{{4}})"
_P = r"(?:present|current|now|today|ongoing|to date)"
RANGE = re.compile(rf"(?<![\w/.])({_D})\s*(?:-|–|—|to|until|till)\s*({_D}|{_P})(?![\w])", re.I)
_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}


def _parse_date(token: str, *, end: bool, today: date) -> tuple[int, str]:
    """(month index = year*12+month, style). Year-only dates lean towards what shortens a gap, so a gap is only reported when it is certain."""
    t = token.strip().lower()
    if re.fullmatch(_P, t):
        return today.year * 12 + today.month, "present"
    m = re.fullmatch(rf"({_MON})\s+(\d{{4}})", t)
    if m:
        word = m.group(1).rstrip(".")
        style = "mon_short" if len(word) <= 3 or word == "sept" else "mon_long"
        return int(m.group(2)) * 12 + _MONTHS[word[:3]], style
    m = re.fullmatch(r"(\d{1,2})[/.](\d{4})", t)
    if m:
        return int(m.group(2)) * 12 + min(max(int(m.group(1)), 1), 12), "numeric"
    m = re.fullmatch(r"(\d{4})-(\d{2})", t)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2)), "iso"
    year = int(t[:4])
    month = 12 if end else 1
    if end and year == today.year:
        month = today.month
    return year * 12 + month, "year"


# --- structure ----------------------------------------------------------------------------------------------------------------------
_BULLET = re.compile(r"^\s*(?:[-*•▪◦●]|\d+[.)])\s+(.*)$")
_HEADING = re.compile(r"^\s*(#{1,6})\s+(.*?)\s*#*\s*$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)[^\s)>\]]+|(?:linkedin|github|gitlab)\.com/[^\s)>\]]+", re.I)
_PHONE = re.compile(r"\+?\(?\d[\d\s().-]{6,}\d")
_MDLINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿■-➿⬀-⯿️]")
_OK_SYMBOLS = set("•·▪◦–—…")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _norm_heading(text: str) -> str:
    text = re.sub(r"[*_`]", "", text).lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def _heading_of(line: str, first_content: bool) -> tuple[int, str] | None:
    """(level, text) when the line is a heading. A lone ALL-CAPS line of a few words also counts, as many CVs write sections that way."""
    m = _HEADING.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip()
    s = line.strip()
    if not first_content and 3 <= len(s) <= 40 and s.upper() == s and re.fullmatch(r"[A-Z &/]+", s) and len(s.split()) <= 4 and not _BULLET.match(line):
        return 2, s
    return None


class Parsed:
    """The CV split into the pieces the checks use."""

    def __init__(self, markdown: str):
        self.text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
        self.lines = self.text.split("\n")
        self.sections: list[dict] = []  # {key, name, level, line, norm}
        self.section_of: dict[int, str | None] = {}  # line number (1-based) -> section key
        current: str | None = None
        seen_content = False
        self.name_line: int | None = None
        for number, line in enumerate(self.lines, start=1):
            if not line.strip():
                self.section_of[number] = current
                continue
            heading = _heading_of(line, first_content=not seen_content)
            if heading and heading[0] == 1 and self.name_line is None and not seen_content:
                self.name_line = number
                seen_content = True
                self.section_of[number] = None
                continue
            seen_content = True
            if heading:
                norm = _norm_heading(heading[1])
                key = _FLAT.get(norm) or ("other" if norm in KNOWN_OTHER else "creative")
                self.sections.append({"key": key, "name": heading[1], "level": heading[0], "line": number, "norm": norm})
                current = key if key not in ("creative",) else "other"
                self.section_of[number] = current
            else:
                self.section_of[number] = current
        first_section = self.sections[0]["line"] if self.sections else min(len(self.lines) + 1, 9)
        self.header_lines = [(n, self.lines[n - 1]) for n in range(1, first_section) if self.lines[n - 1].strip()]
        self.is_heading = {n for n in range(1, len(self.lines) + 1) if self.lines[n - 1].strip() and _heading_of(self.lines[n - 1], False)}

    def keys(self) -> set[str]:
        return {s["key"] for s in self.sections}

    def section_text(self, *keys: str) -> str:
        return "\n".join(self.lines[n - 1] for n, k in self.section_of.items() if k in keys and n not in self.is_heading)

    def lines_in(self, *keys: str, exclude: bool = False):
        for n, line in enumerate(self.lines, start=1):
            if not line.strip() or n in self.is_heading:
                continue
            inside = self.section_of.get(n) in keys
            if inside != exclude:
                yield n, line


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\s#*_`|>]+", text) if re.search(r"\w", w)]


def looks_english(text: str) -> bool:
    words = [w.lower() for w in re.findall(r"[^\W\d_]+", text)]
    if len(words) < 25:
        return True
    english = sum(1 for w in words if w in _ENGLISH_COMMON) / len(words)
    foreign = sum(1 for w in words if w in _FOREIGN_COMMON) / len(words)
    return not (foreign >= 0.05 and foreign > english)


def _lines_text(numbers: list[int]) -> list[int]:
    return sorted(set(numbers))[:8]


def _check(cid, group, status, title, why, fix, weight, lines=None) -> dict:
    return {"id": cid, "group": group, "status": status, "title": title, "why": why, "fix": "" if status == "pass" else fix, "weight": weight, "lines": _lines_text(lines or [])}


# --- the checks ---------------------------------------------------------------------------------------------------------------------
def _contact(p: Parsed) -> list[dict]:
    out = []
    header = "\n".join(line for _, line in p.header_lines)
    whole = p.text
    email = _EMAIL.search(header) or _EMAIL.search(whole)
    out.append(
        _check("contact_email", "Contact details", "pass" if email else "fail",
               "Email address found" if email else "No email address found",
               "Recruiters and tracking systems use your email as your identity and the first way to reach you.",
               "Put your email address on its own line right under your name.", 8)
    )
    phone = None
    for source in (header, whole):
        for m in _PHONE.finditer(source):
            digits = re.sub(r"\D", "", m.group(0))
            if 8 <= len(digits) <= 15 and not RANGE.search(m.group(0)):
                phone = m
                break
        if phone:
            break
    out.append(
        _check("contact_phone", "Contact details", "pass" if phone else "warn",
               "Phone number found" if phone else "No phone number found",
               "Many employers still call first, and some systems ask for a phone number.",
               "Add a phone number with the country code, such as +60 12 345 6789, under your name.", 3)
    )
    place = False
    for _, line in p.header_lines:
        for seg in re.split(r"[|·•]", line):
            seg = re.sub(r"[*_`#]", "", seg).strip()
            if re.match(r"^(location|based in|address|city)\s*[:\-]", seg, re.I) or re.fullmatch(r"remote( \(.*\))?", seg, re.I):
                place = True
            elif re.fullmatch(r"[^\W\d_][^\d@,|]{1,40},\s*[^\W\d_][^\d@,|]{1,40}", seg) and seg[0].isupper() and len(seg.split()) <= 6:
                place = True
    out.append(
        _check("contact_location", "Contact details", "pass" if place else "warn",
               "City or country found" if place else "No city or country found",
               "Employers filter by where you are, and a missing place can drop you from a local search.",
               "Add your city and country, such as Kuala Lumpur, Malaysia, in the header. If you want remote work, say so as well.", 3)
    )
    link = _URL.search(header) or _URL.search(whole)
    out.append(
        _check("contact_link", "Contact details", "pass" if link else "warn",
               "Profile or portfolio link found" if link else "No profile or portfolio link found",
               "A LinkedIn, GitHub or portfolio address lets a reader see more than one page can hold.",
               "Add one link, written out in full (for example linkedin.com/in/yourname), in the header.", 3)
    )
    bad_lines, soft_lines, found = [], [], []
    hard = re.compile(
        r"date of birth|\bdob\b|born on|\bage\s*[:\-]\s*\d|\bmarital status\b|\b(?:married|unmarried|divorced)\b|"
        r"\b(?:passport(?: no| number)?|national id|social security|aadhaar|nric|ssn)\b|!\[|<img|\bphoto(?:graph)?\s*[:\-]",
        re.I,
    )
    soft = re.compile(r"\b(?:nationality|gender|religion|sex)\s*[:\-]", re.I)
    for n, line in enumerate(p.lines, start=1):
        m = hard.search(line)
        if m:
            bad_lines.append(n)
            found.append(m.group(0).lower())
        elif soft.search(line):
            soft_lines.append(n)
    if bad_lines:
        out.append(_check("contact_extras", "Contact details", "fail", "Personal details that should not be on a CV",
                          "Photos, age, marital status and ID numbers are not needed to judge your work, and many employers are not allowed to ask for them.",
                          "Remove the photo, date of birth, marital status and any ID or passport number.", 4, bad_lines))
    elif soft_lines:
        out.append(_check("contact_extras", "Contact details", "warn", "Personal details you could leave out",
                          "Nationality, gender or religion are not needed to judge your work.", "Remove them unless the posting asks for it.", 4, soft_lines))
    else:
        out.append(_check("contact_extras", "Contact details", "pass", "No photo, age or ID numbers",
                          "Nothing in the CV is personal detail an employer has no need for.", "", 4))
    return out


def _sections(p: Parsed) -> list[dict]:
    out = []
    keys = p.keys()
    has_work = "experience" in keys or any(s["norm"] in {"projects", "personal projects", "selected projects", "key projects"} for s in p.sections)
    missing = []
    if not has_work:
        missing.append("Work experience")
    if "education" not in keys:
        missing.append("Education")
    if "skills" not in keys:
        missing.append("Skills")
    if not has_work:
        status = "fail"
    elif missing:
        status = "warn"
    else:
        status = "pass"
    why = "Parsers sort a CV by its section headings, so a missing core section can leave that part of your story out."
    if "summary" not in keys:
        why += " A short Summary at the top is also worth having."
    out.append(
        _check("sections_present", "Sections", status,
               "The main sections are all there" if status == "pass" else f"Missing: {', '.join(missing)}", why,
               f"Add a heading for {', '.join(missing)}. If you have no paid experience yet, list projects or volunteering under Work experience.", 10)
    )
    creative = [s for s in p.sections if s["key"] == "creative"]
    if creative:
        bits = []
        for s in creative:
            hint = next((key for words, key in _HINTS if any(w in s["norm"] for w in words)), None)
            bits.append(f'"{s["name"]}" could be "{STANDARD_NAME[hint]}"' if hint else f'"{s["name"]}" is not a name parsers know (use Summary, Work experience, Education or Skills)')
        out.append(_check("sections_names", "Sections", "warn", "Some headings have creative names",
                          "Tracking systems look for common heading names. A heading such as " + bits[0] + " may not be recognised, so what is under it can be misfiled.",
                          "Rename: " + "; ".join(bits) + ".", 5, [s["line"] for s in creative]))
    elif p.sections:
        out.append(_check("sections_names", "Sections", "pass", "Headings use common names", "Parsers know these heading names.", "", 5))
    return out


def _ranges(p: Parsed, today: date) -> list[dict]:
    found = []
    for n, line in p.lines_in("education", "skills", "summary", "certifications", "languages", exclude=True):
        for m in RANGE.finditer(line):
            start, s_style = _parse_date(m.group(1), end=False, today=today)
            end, e_style = _parse_date(m.group(2), end=True, today=today)
            found.append({"start": start, "end": end, "line": n, "styles": {s_style, e_style} - {"present"}})
    return found


def _dates(p: Parsed, today: date) -> tuple[list[dict], list[dict]]:
    out = []
    rngs = _ranges(p, today)
    has_work = "experience" in p.keys()
    if has_work and not rngs:
        out.append(_check("dates_format", "Dates", "warn", "No dates found in your experience",
                          "Parsers build your timeline from dates, and employers read missing dates as something to explain.",
                          "Give each job a date range such as Jan 2022 - Mar 2024 (or 2022 - Present).", 5))
        return out, rngs
    if not rngs:
        return out, rngs
    styles = set().union(*(r["styles"] for r in rngs))
    labels = {"mon_short": "Jan 2022", "mon_long": "January 2022", "numeric": "03/2022", "iso": "2022-03", "year": "2022"}
    if len(styles) > 1:
        out.append(_check("dates_format", "Dates", "warn", "Dates are written in more than one style",
                          "Mixed styles (" + ", ".join(labels[s] for s in sorted(styles)) + ") are harder for a parser to read as one timeline.",
                          "Pick one style, such as Jan 2022 - Mar 2024, and use it for every job.", 5, [r["line"] for r in rngs]))
    else:
        out.append(_check("dates_format", "Dates", "pass", "Dates use one clear style", "Every date range is written the same way, so a parser can read your timeline.", "", 5))
    if len(rngs) >= 2:
        bad = [b["line"] for a, b in zip(rngs, rngs[1:]) if a["start"] < b["start"]]
        if bad:
            out.append(_check("dates_order", "Dates", "warn", "Jobs are not newest first",
                              "Most systems and readers expect your latest job first, and some take the first entry as your current role.",
                              "Reorder the jobs so the most recent is at the top and the oldest at the bottom.", 5, bad))
        else:
            out.append(_check("dates_order", "Dates", "pass", "Jobs run newest first", "Your latest role comes first, as parsers expect.", "", 5))
    ordered = sorted(rngs, key=lambda r: r["start"])
    latest_end, gaps = None, []
    for r in ordered:
        if latest_end is not None and r["start"] - latest_end - 1 > 12:
            gaps.append((r["line"], r["start"] - latest_end - 1))
        latest_end = r["end"] if latest_end is None else max(latest_end, r["end"])
    if gaps:
        months = max(g for _, g in gaps)
        out.append(_check("gaps", "Dates", "warn", f"A gap of about {months} months between jobs",
                          "This is a fact about the dates on the page, not a verdict on you. A reader may simply wonder what happened.",
                          "If you want, add one plain line for that time (study, caring, travel, freelance, health). You do not have to.", 3, [g[0] for g in gaps]))
    elif len(rngs) >= 2:
        out.append(_check("gaps", "Dates", "pass", "No gap longer than 12 months", "The dates on the page leave no stretch of more than a year unexplained.", "", 3))
    return out, rngs


def _length(p: Parsed, rngs: list[dict], today: date) -> tuple[dict, dict]:
    words = len(_words(p.text))
    pages = max(1, math.ceil(words / 550))
    early = True
    if rngs:
        early = (today.year * 12 + today.month - min(r["start"] for r in rngs)) < 60
    if words < 150:
        status, why, fix = "warn", "Very little text means little for a parser or a reader to match.", "Add a summary, your roles and what you achieved in each."
        title = f"Short: about {words} words"
    elif words > 1100:
        status, why, fix = "warn", "Three or more pages is more than most recruiters read.", "Cut older or less relevant roles and keep each to its best 3 to 5 bullets."
        title = f"Long: about {words} words, roughly {pages} pages"
    elif early and words > 750:
        status, why, fix = "warn", "With under about five years of experience, one page (around 600 words) is the usual expectation.", "Trim to your strongest points so it fits on one page."
        title = f"Longer than usual for early career: about {words} words"
    else:
        status, why, fix = "pass", "A length most employers will read.", ""
        title = f"Good length: about {words} words, roughly {pages} page{'s' if pages > 1 else ''}"
    return _check("length", "Length", status, title, why, fix, 5), {"words": words, "pages": pages}


def _bullets(p: Parsed, english: bool) -> tuple[list[dict], dict]:
    out, stats = [], {}
    items = []  # (line number, text)
    for n, line in p.lines_in("skills", "education", "summary", "languages", "certifications", exclude=True):
        m = _BULLET.match(line)
        if m and m.group(1).strip():
            items.append((n, re.sub(r"[*_`]", "", m.group(1)).strip()))
    stats["bullets"] = len(items)
    paragraphs = [n for n, line in p.lines_in("skills", "education", exclude=True) if not _BULLET.match(line) and len(line.split()) > 60]
    if paragraphs:
        out.append(_check("long_paragraphs", "Bullets", "warn", "A very long paragraph",
                          "Dense blocks of text are skimmed or skipped by readers and are hard for parsers to split into achievements.",
                          "Break it into bullets of one achievement each.", 2, paragraphs))
    else:
        out.append(_check("long_paragraphs", "Bullets", "pass", "No very long paragraphs", "The text is broken into readable pieces.", "", 2))
    if len(items) < 3:
        return out, stats
    total = len(items)
    if english:
        strong, weak_lines = 0, []
        for n, text in items:
            first = re.sub(r"[^\w']", "", text.split()[0]).lower() if text.split() else ""
            if not _WEAK_START.match(text) and (first in VERBS or (first.endswith("ed") and len(first) > 3) or (first.endswith("ing") and len(first) > 4)):
                strong += 1
            else:
                weak_lines.append(n)
        share = strong / total
        if share >= 0.6:
            out.append(_check("bullets_verb", "Bullets", "pass", f"{round(share * 100)}% of bullets start with an action word", "Starting with what you did (Built, Led, Reduced) makes each line a result.", "", 6))
        else:
            out.append(_check("bullets_verb", "Bullets", "fail" if share < 0.3 else "warn", f"Only {round(share * 100)}% of bullets start with an action word",
                              "Lines that start with \"Responsible for\" or a noun say what the job was, not what you did.",
                              "Start each bullet with a verb such as Built, Led, Reduced or Launched, keeping the facts the same.", 6, weak_lines))
    long_or_short = [n for n, text in items if len(text.split()) > 35 or len(text.split()) < 4]
    if len(long_or_short) / total > 0.25:
        out.append(_check("bullets_length", "Bullets", "warn", "Many bullets are very long or very short",
                          "Bullets of about 8 to 25 words are read; longer ones are skimmed and tiny ones say nothing.",
                          "Aim for one clear line of 8 to 25 words each, with what you did and what it achieved.", 3, long_or_short))
    else:
        out.append(_check("bullets_length", "Bullets", "pass", "Bullets are a readable length", "Most bullets are short enough to skim and long enough to say something.", "", 3))
    with_number = sum(1 for _, text in items if re.search(r"\d", text))
    share = with_number / total
    stats["numbers_share"] = round(share, 2)
    if share >= 0.3:
        out.append(_check("bullets_numbers", "Bullets", "pass", f"{round(share * 100)}% of bullets include a number", "Numbers (people, money, time, scale) make a result believable.", "", 8))
    else:
        out.append(_check("bullets_numbers", "Bullets", "fail" if with_number == 0 and total >= 4 else "warn", f"Only {with_number} of {total} bullets include a number",
                          "Results with a number (a count, a percentage, a time saved) are remembered and are what recruiters search for.",
                          "Where it is true, add the real figure to a few bullets. Do not make one up: leave it out if you do not know it.", 8,
                          [n for n, text in items if not re.search(r"\d", text)]))
    if english:
        fp = [n for n, text in items if _FIRST_PERSON.search(text)]
        fp += [n for n, line in p.lines_in("skills", "education", exclude=True) if not _BULLET.match(line) and _FIRST_PERSON.search(line) and len(line.split()) > 8]
        if fp:
            out.append(_check("first_person", "Wording", "warn", "First-person words (I, my, me) in the text",
                              "A CV reads as stronger and shorter without \"I\" and \"my\".", "Drop them: \"I led my team\" becomes \"Led a team\".", 3, fp))
        else:
            out.append(_check("first_person", "Wording", "pass", "No first-person words", "The text is written in the plain CV style.", "", 3))
        passive = [n for n, text in items if _PASSIVE.search(text)]
        if len(passive) >= 2:
            out.append(_check("passive", "Wording", "warn", "Filler phrases such as \"responsible for\"",
                              "Phrases like \"responsible for\" and \"worked on\" describe a duty, not a result.",
                              "Replace them with what you did and what came of it.", 2, passive))
        else:
            out.append(_check("passive", "Wording", "pass", "No filler phrases", "Few or no \"responsible for\" style phrases.", "", 2))
        firsts = Counter(re.sub(r"[^\w]", "", text.split()[0]).lower() for _, text in items if text.split())
        word, count = firsts.most_common(1)[0]
        if count >= 3 and count / total >= 0.3:
            out.append(_check("bullets_repeat", "Wording", "warn", f"\"{word.capitalize()}\" starts {count} bullets",
                              "The same opening word again and again makes the list read as a copy.", "Vary the openings: Led, Built, Reduced, Launched, Trained.", 2,
                              [n for n, text in items if text.split() and re.sub(r"[^\w]", "", text.split()[0]).lower() == word]))
        else:
            out.append(_check("bullets_repeat", "Wording", "pass", "Bullet openings vary", "No opening word is overused.", "", 2))
    return out, stats


def _characters(p: Parsed) -> list[dict]:
    out = []
    table = [n for n, line in enumerate(p.lines, start=1) if _TABLE_SEP.match(line) or (_TABLE_ROW.match(line) and line.count("|") >= 3)]
    out.append(
        _check("no_tables", "Layout and characters", "fail" if table else "pass",
               "A table is used" if table else "No tables",
               "Parsers read tables cell by cell and often scramble the order, mixing dates with the wrong job.",
               "Replace the table with headings and bullets. Our export is already a single plain column.", 6, table)
        if table else _check("no_tables", "Layout and characters", "pass", "No tables", "Nothing is laid out in a table, so a parser reads the CV in order.", "", 6)
    )
    cols = [n for n, line in enumerate(p.lines, start=1) if "\t" in line or re.search(r"\S {4,}\S", line) or (line.count("|") >= 3 and not _TABLE_ROW.match(line))]
    if cols:
        out.append(_check("no_columns", "Layout and characters", "warn", "Columns drawn with tabs, spaces or pipes",
                          "Text lined up in columns is read straight across, which mixes the left and right sides together.",
                          "Put each item on its own line, or separate items with commas.", 3, cols))
    else:
        out.append(_check("no_columns", "Layout and characters", "pass", "No columns", "Everything is in one column.", "", 3))
    sym_lines, symbols = [], []
    for n, line in enumerate(p.lines, start=1):
        hit = [c for c in _EMOJI.findall(line) if c not in _OK_SYMBOLS]
        if hit:
            sym_lines.append(n)
            symbols += hit
    if sym_lines:
        out.append(_check("no_symbols", "Layout and characters", "warn", "Emoji or decorative symbols (" + " ".join(dict.fromkeys(symbols[:4])) + ")",
                          "Many parsers drop or garble symbols, and an icon in front of an email or phone number can hide it.",
                          "Use plain words and a simple dot bullet instead of icons.", 3, sym_lines))
    else:
        out.append(_check("no_symbols", "Layout and characters", "pass", "No emoji or decorative symbols", "Only plain characters are used.", "", 3))
    mojibake = [n for n, line in enumerate(p.lines, start=1) if re.search(r"Ã.|â€|�", line)]
    invisible = [n for n, line in enumerate(p.lines, start=1) if re.search(r"[​‌‍⁠﻿­ ]", line)]
    curly = len(re.findall(r"[“”‘’]", p.text))
    straight = len(re.findall(r'"', p.text)) + len(re.findall(r"\w'\w", p.text))
    if mojibake:
        out.append(_check("clean_text", "Layout and characters", "fail", "Damaged characters",
                          "Strange letters such as Ã or � mean the text was saved with the wrong encoding, and a parser will read them literally.",
                          "Retype those words, or paste the text again as plain text.", 3, mojibake))
    elif invisible or (curly and straight):
        why = "Invisible spaces and a mix of curly and straight quotes can split words or break keyword matching." if invisible else "Mixing curly and straight quotes is a sign of pasted text, and can break keyword matching."
        out.append(_check("clean_text", "Layout and characters", "warn", "Hidden or mixed characters", why, "Paste the text as plain text and use one kind of quote.", 3, invisible))
    else:
        out.append(_check("clean_text", "Layout and characters", "pass", "Clean characters", "No damaged or invisible characters.", "", 3))
    page_re = re.compile(r"^\W*(?:page\s+\d+(?:\s+(?:of|/)\s+\d+)?|\d+\s*/\s*\d+|curriculum vitae|resume|cv|confidential)\W*$", re.I)
    hf = [n for n, line in enumerate(p.lines, start=1) if page_re.match(line) and line.strip()]
    counts = Counter(line.strip().lower() for line in p.lines if len(line.split()) >= 3 and not _BULLET.match(line) and not _HEADING.match(line))
    repeated = [n for n, line in enumerate(p.lines, start=1) if counts.get(line.strip().lower(), 0) >= 2]
    if hf or repeated:
        out.append(_check("no_header_footer", "Layout and characters", "warn", "Looks like a page header or footer",
                          "Page numbers and lines repeated on every page get read as part of your experience, and many parsers skip real headers and footers altogether.",
                          "Remove page numbers, \"Curriculum Vitae\" titles and repeated lines. Keep your contact details in the body, not a header.", 2, hf + repeated))
    else:
        out.append(_check("no_header_footer", "Layout and characters", "pass", "No header or footer text", "Nothing looks like a repeated page header or footer.", "", 2))
    return out


def _skills(p: Parsed) -> list[dict]:
    out = []
    text = p.section_text("skills")
    if not text.strip():
        return out
    items = []
    for line in text.split("\n"):
        line = _BULLET.sub(r"\1", line)
        line = re.sub(r"[*_`]", "", line)
        if ":" in line[:35]:
            line = line.split(":", 1)[1]
        line = re.sub(r"[()]", ",", line)
        for raw in re.split(r"[,;|•·]", line):
            item = raw.strip(" .-\t")
            if item and 1 <= len(item.split()) <= 4 and len(item) <= 40:
                items.append(item)
    if not items:
        return out
    seen, dupes = {}, []
    for item in items:
        k = item.casefold()
        if k in seen and item not in dupes:
            dupes.append(item)
        seen[k] = True
    if dupes:
        out.append(_check("skills_dupes", "Skills", "warn", "Skills listed twice: " + ", ".join(dupes[:4]),
                          "A repeated skill adds nothing and can look like padding.", "List each skill once.", 2))
    else:
        out.append(_check("skills_dupes", "Skills", "pass", "No repeated skills", "Each skill appears once.", "", 2))
    if len(seen) > 25:
        out.append(_check("skills_count", "Skills", "warn", f"{len(seen)} skills listed",
                          "A very long list is skimmed and makes the strongest skills harder to see.", "Keep the 12 to 20 you use most and can talk about.", 2))
    else:
        out.append(_check("skills_count", "Skills", "pass", f"{len(seen)} skills listed", "A list of a size a reader can take in.", "", 2))
    body = p.section_text("experience", "projects", "other").lower()
    if len(body.split()) >= 15:
        missing = [i for i in dict.fromkeys(items) if i.casefold() not in _SOFT and not re.search(r"(?<!\w)" + re.escape(i.casefold()) + r"(?!\w)", body)]
        total = len([i for i in dict.fromkeys(items) if i.casefold() not in _SOFT])
        if total and len(missing) >= 4 and len(missing) / total >= 0.5:
            out.append(_check("skills_in_experience", "Skills", "warn", f"{len(missing)} listed skills never appear in your experience",
                              "Employers trust a skill more when a job or project shows it in use (for example: " + ", ".join(missing[:4]) + ").",
                              "Where it is true, mention the skill in the bullet where you used it. Remove a skill you could not talk about in an interview.", 3))
        else:
            out.append(_check("skills_in_experience", "Skills", "pass", "Listed skills are backed by your experience", "Most skills in the list show up in your jobs or projects.", "", 3))
    return out


def _acronyms_and_links(p: Parsed) -> list[dict]:
    out = []
    low = p.text.lower()
    unexpanded = [a for a, expansion in ACRONYMS.items() if re.search(rf"(?<![\w/]){re.escape(a)}(?![\w/])", p.text) and not re.search(expansion, low)]
    if unexpanded:
        out.append(_check("acronyms", "Wording", "warn", "Acronyms with no spelled-out form: " + ", ".join(unexpanded[:5]),
                          "A recruiter may search for the long form and a system may only know the short one. Writing both once catches both.",
                          "Write it in full the first time, then the short form in brackets: " + f"{unexpanded[0]} -> its full name ({unexpanded[0]}).", 2))
    else:
        out.append(_check("acronyms", "Wording", "pass", "Acronyms are spelled out where it helps", "Nothing needs both forms, or both are already there.", "", 2))
    links = _MDLINK.findall(p.text)
    bad_links = []
    for text, url in links:
        if text.strip().lower() in _GENERIC_LINK or any(s in url.lower() for s in _SHORTENERS):
            bad_links.append(text)
    bad_lines = [n for n, line in enumerate(p.lines, start=1) if any(_MDLINK.search(line) and (t in line) for t in bad_links)] if bad_links else []
    shorteners = [n for n, line in enumerate(p.lines, start=1) if any(s in line.lower() for s in _SHORTENERS)]
    if bad_links or shorteners:
        out.append(_check("links_visible", "Wording", "warn", "A link says \"here\" or hides its address",
                          "A reader or a parser needs to see where a link goes. Words such as \"here\" or a shortened address tell them nothing.",
                          "Write the real address in full, such as github.com/yourname.", 1, bad_lines + shorteners))
    else:
        out.append(_check("links_visible", "Wording", "pass", "Links are readable", "Addresses are written out, and our export spells out any link text as its full address.", "", 1))
    return out


def _export_check() -> dict:
    return _check("export_format", "File format", "pass", "StillOpen's file is built to be ATS-safe", EXPORT["summary"] + " Upload the DOCX unless the posting asks for a PDF, and save it as FirstName-LastName-CV.", "", 0)


def _label(score: int) -> str:
    return "Strong" if score >= 85 else "Good start" if score >= 65 else "Needs work" if score >= 40 else "Needs a lot of work"


def check_text(markdown: str, today: date | None = None) -> dict:
    """The full rule-based check of one CV. Never raises on odd input (empty, not English, binary-looking)."""
    today = today or date.today()
    text = (markdown or "").replace("\x00", "")
    if not _words(text):
        empty = _check("not_empty", "Basics", "fail", "The CV is empty", "There is nothing for a tracking system to read.", "Add your CV, or build one step by step.", 10)
        return {"readiness": 0, "label": _label(0), "caveat": CAVEAT, "checks": [empty], "counts": {"pass": 0, "warn": 0, "fail": 1}, "stats": {"words": 0, "pages": 0, "bullets": 0}, "export": EXPORT, "notes": [], "empty": True}
    p = Parsed(text)
    english = looks_english(text)
    notes = [] if english else ["This CV does not look like English, so the checks on action words, first person and filler phrases were skipped. Everything else was checked."]
    checks = _contact(p) + _sections(p)
    date_checks, rngs = _dates(p, today)
    checks += date_checks
    length, stats = _length(p, rngs, today)
    checks.append(length)
    bullet_checks, bullet_stats = _bullets(p, english)
    checks += bullet_checks + _characters(p) + _skills(p) + _acronyms_and_links(p)
    stats.update(bullet_stats)
    if stats.get("bullets", 0) < 3:
        notes.append("Fewer than three bullets were found, so the checks on bullet wording and numbers were skipped. Use a dash and a space to start each bullet.")
    checks.append(_export_check())
    points = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    total_w = sum(c["weight"] for c in checks)
    readiness = round(100 * sum(c["weight"] * points[c["status"]] for c in checks) / total_w) if total_w else 0
    counts = Counter(c["status"] for c in checks)
    return {
        "readiness": readiness, "label": _label(readiness), "caveat": CAVEAT, "checks": checks,
        "counts": {k: counts.get(k, 0) for k in ("pass", "warn", "fail")}, "stats": stats, "export": EXPORT, "notes": notes, "empty": False,
    }


# --- keyword coverage against a job -------------------------------------------------------------------------------------------------
_REQUIRED_LINE = re.compile(r"\b(must|required|requirements?|essential|minimum|proficien\w+|expert\w*|strong|experience (?:in|with)|you have|you will need|need to)\b", re.I)


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def coverage(cv_text: str, job_text: str, material: list[str], ignore=frozenset()) -> dict | None:
    """Which of the posting's most repeated terms the CV has, split by whether the person's own material could back a missing one.

    `ignore` is the filler every posting repeats (the same recipe `ai.keyword_match` uses). Returns None when the posting has nothing to compare."""
    ranked = [w for w, _ in Counter(terms(job_text)).most_common(120)]
    wanted = [w for w in ranked if w not in ignore][:40] or ranked[:40]
    if not wanted:
        return None
    required = set()
    for line in job_text.splitlines():
        if _REQUIRED_LINE.search(line):
            required.update(terms(line))
    have_cv = {_stem(t) for t in terms(cv_text)}
    have_material = {_stem(t) for t in terms("\n".join(material))}
    found, in_material, outside = [], [], []
    for w in sorted(wanted, key=lambda t: (t not in required, wanted.index(t))):
        entry = {"term": w, "required": w in required}
        if _stem(w) in have_cv:
            found.append(entry)
        elif _stem(w) in have_material:
            in_material.append(entry)
        else:
            outside.append(entry)
    return {
        "percent": round(100 * len(found) / len(wanted)), "wanted": len(wanted), "found": found,
        "in_material": in_material, "not_in_material": outside,
        "note": (
            "Only add a word from the first list if it is true. The words in the second list are not in your own CV or documents, so leave them out "
            "unless you really have that skill: if you do, add it to your documents first."
        ),
    }


def cached_readiness(version_id: int, content: str) -> int:
    """The readiness number of a saved CV version. A version never changes, so the number is remembered; the CV list shows one per row."""
    from django.core.cache import cache

    key = f"ats-readiness:{version_id}:{ENGINE}"
    value = cache.get(key)
    if value is None:
        value = check_text(content)["readiness"]
        cache.set(key, value, 24 * 3600)
    return value
