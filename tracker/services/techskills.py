"""A real, named-technology vocabulary for job postings and CVs -- Docker, Kubernetes, React, Terraform... --
grounded in the US Department of Labor's O*NET database rather than generic word-frequency.

Why this exists: the free keyword match (ai.keyword_match) compares whichever words a posting repeats most
against the candidate's CV, which is a fine zero-token fallback but has no idea which of those words name an
actual tool a hiring manager cares about versus filler. ESCO (the EU's skills taxonomy) was tried for this and
rejected (see docs/ROADMAP.md): live-checked, it returned zero hits for "docker" and "kubernetes" and only noisy
soft-skill matches for "react". O*NET's own "Software Skills" table (part of its Tools & Technology content
model) is different -- live-checked the same way, it genuinely lists specific products per occupation (28 rows
mention Docker, 15 mention Kubernetes, Software Developers alone lists React, Django, TypeScript...), each
flagged "Hot Technology" when it is one O*NET's own employer-postings analysis shows is actually in demand.

Bundled as `tracker/data/onet_tech_skills.json` (8,741 distinct product names, deduplicated from O*NET's public
`software_skills.csv`, release 31.0) rather than called live: this is reference data, not something that
changes search results day to day, so there is no reason to make a network call for it. A handful of single
word, high-collision entries (`C`, `R`, `Go`, `J`...) were dropped from the source file -- too likely to match
an ordinary English sentence rather than the technology.

O*NET® is a trademark of the U.S. Department of Labor, Employment and Training Administration. The O*NET
database is licensed under a Creative Commons Attribution 4.0 International License
(https://creativecommons.org/licenses/by/4.0/) -- see https://www.onetcenter.org/license_db.html.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "onet_tech_skills.json"
MAX_RECOGNIZED = 12


@lru_cache(maxsize=1)
def _catalog() -> list[tuple[str, bool]]:
    return [tuple(row) for row in json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))]


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern:
    # Longest names first, so "Amazon Web Services" matches whole rather than stopping at a shorter entry
    # that happens to be a prefix of it.
    names = sorted((name for name, _ in _catalog()), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)


def _found_in(text: str) -> dict[str, bool]:
    """Every catalog name that appears in `text`, by its canonical (not the matched) casing, with its "hot" flag."""
    if not text.strip():
        return {}
    hot_by_lower = {name.lower(): hot for name, hot in _catalog()}
    canonical_by_lower = {name.lower(): name for name, _ in _catalog()}
    seen = {}
    for m in _pattern().finditer(text):
        lower = m.group(1).lower()
        name = canonical_by_lower.get(lower)
        if name is not None:
            seen[name] = hot_by_lower.get(lower, False)
    return seen


def recognized(description: str, cv_text: str) -> list[dict]:
    """Real, named technologies this posting mentions, each marked whether the candidate's own material already
    covers it. Hot (in-demand, per O*NET) technologies sort first; returns [] when the posting names none --
    a sales or operations role, say -- rather than forcing an empty or misleading panel onto every job card."""
    in_posting = _found_in(description)
    if not in_posting:
        return []
    have = _found_in(cv_text)
    rows = [{"name": name, "hot": hot, "have": name in have} for name, hot in in_posting.items()]
    rows.sort(key=lambda r: (not r["hot"], r["have"], r["name"].lower()))
    return rows[:MAX_RECOGNIZED]
