"""Does a tailored CV claim anything the candidate's own material does not support?

Deliberately conservative: it flags, it does not judge. Three kinds of finding:
  number    a figure, year or count that is not in the source ("10,000 users", "8 years", "2021")
  name      a capitalised word in the middle of a sentence that is not in the source (an employer, tool or school)
  job-term  a term the job posting uses, that the source never mentions, but the CV now does (keyword stuffing)
The person reviews flagged items and approves them if they are in fact true.
"""
import re

from tracker.services.text import terms

_NUMBER = re.compile(r"\d[\d,.]*\d|\d")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.&'/-]*")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")

# Capitalised words that are ordinary in any CV and need no support from the source.
COMMON = {
    "i", "a", "an", "the", "and", "or", "of", "to", "in", "at", "for", "with", "on", "by", "as", "from",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "present", "current", "remote", "hybrid", "full-time", "part-time", "present.", "etc", "e.g", "i.e",
    "english", "references", "available", "upon", "request",
    "experience", "education", "skills", "summary", "projects", "profile", "certifications", "languages", "professional",
    "technical", "work", "employment", "history", "achievements", "objective", "contact", "interests", "awards",
    "publications", "volunteer", "core", "competencies", "key", "selected", "additional", "tools", "technologies",
}


def _norm_number(raw: str) -> str:
    return raw.replace(",", "").strip(".")


def _numbers(text: str) -> set[str]:
    return {_norm_number(m) for m in _NUMBER.findall(text) if _norm_number(m)}


def _vocabulary(texts: list[str]) -> set[str]:
    words = set()
    for text in texts:
        for w in _WORD.findall(text):
            words.add(w.lower().rstrip(".,;:"))
    return words


def _candidate_names(line: str) -> list[str]:
    """Capitalised words that could be an employer, school or tool.

    In a bullet or a running sentence the first word of each sentence is skipped (verbs like "Built"). In any other
    line, such as an employer line or a plain heading, every capitalised word counts, so an invented employer on a
    line of its own is still caught."""
    is_bullet = bool(_BULLET.match(line))
    stripped = _BULLET.sub("", line.strip())
    out = []
    for match in _WORD.finditer(stripped):
        word = match.group(0)
        if not word[0].isupper():
            continue
        before = stripped[: match.start()].rstrip()
        sentence_start = not before or before[-1] in ".!?"
        if sentence_start and (is_bullet or stripped.rstrip().endswith((".", "!", "?"))):
            continue
        out.append(word)
    return out


def fact_check(generated: str, sources: list[str], job_text: str = "") -> list[dict]:
    """Findings for `generated` against the person's own `sources` (CV + documents). Empty list = nothing unsupported."""
    source_numbers = set().union(*[_numbers(s) for s in sources]) if sources else set()
    vocab = _vocabulary(sources)
    findings, seen = [], set()

    def add(kind: str, text: str, line_no: int) -> None:
        key = (kind, text.lower())
        if key not in seen:
            seen.add(key)
            findings.append({"kind": kind, "text": text, "line": line_no})

    for number_line, line in enumerate(generated.splitlines(), start=1):
        for raw in _NUMBER.findall(line):
            if _norm_number(raw) not in source_numbers:
                add("number", raw.strip(".,"), number_line)
        if line.lstrip().startswith("#"):
            continue  # headings are structure, not claims
        for word in _candidate_names(line):
            low = word.lower().rstrip(".,;:")
            if low in COMMON or low in vocab or any(low.rstrip("s") == v.rstrip("s") for v in vocab if abs(len(v) - len(low)) <= 1):
                continue
            add("name", word.rstrip(".,;:"), number_line)

    if job_text:
        source_terms = set(terms(" ".join(sources)))
        wanted = set(terms(job_text)) - source_terms
        for term in sorted(wanted & set(terms(generated))):
            line_no = next((i for i, l in enumerate(generated.splitlines(), 1) if term in l.lower()), 0)
            add("job-term", term, line_no)
    return findings
