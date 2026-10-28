"""How you match: what a posting asks for, and for each ask whether the person's own material says it, with where.

Zero-token by default. The posting's requirements are read from its own text (the lines under a heading such as Requirements or What you bring,
years-of-experience and degree phrases, and the named technologies from `techskills`); an AI the person set up themselves may read them instead
(`read_with_ai`), and its answer is only kept for lines that really come from the posting. Each requirement is then looked for in the person's CV and
knowledge sources, line by line: it is ticked only when a line of their material says it, and that line (with where it is from) is shown as the
evidence. Nothing is guessed: a requirement their material does not state is a gap, never a tick.

The requirements are cached per description (they depend only on the posting); the comparison with the person's material is redone each time, so
a fact they add shows up at once. Everything here is for one owner and one of their jobs."""
import hashlib
import re
from math import ceil

from django.core.cache import cache
from django.utils import timezone

from tracker.models import KnowledgeSource, SiteConfig
from tracker.services import assist, knowledge, techskills
from tracker.services.text import terms

MAX_REQUIREMENTS = 12
MAX_LINE = 200
SNIPPET = 160
CACHE_SECONDS = 24 * 3600
MAX_FACT = 300
MAX_FACTS_CHARS = 20_000
FACTS_KEY = "match-facts"  # the one source the "Add to my profile" action appends to
FACTS_TITLE = "Facts I added from job matches"

_BULLET = re.compile(r"^\s*(?:[-*•●▪–]|\d{1,2}[.)])\s+")
_REQ_HEADING = re.compile(
    r"^\W*(?:minimum |basic |preferred |required |essential |key )?(?:requirements?|qualifications?|what you(?:'ll| will)? bring|what we(?:'re| are) looking for|"
    r"what you(?:'ll| will)? need|you have|you bring|who you are|must[- ]haves?|skills(?: and experience| & experience)?|about you|your profile|"
    r"nice[- ]to[- ]haves?|bonus points|experience)\b[^\n]{0,40}$",
    re.I,
)
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)\b", re.I)
_DEGREE_WORDS = {
    1: re.compile(r"\b(?:bachelor'?s?|b\.?sc\.?|b\.?a\.?|b\.?eng\.?|b\.?tech|undergraduate)\b", re.I),
    2: re.compile(r"\b(?:master'?s?|m\.?sc\.?|m\.?eng\.?|mba|m\.?tech|postgraduate)\b", re.I),
    3: re.compile(r"\b(?:ph\.?d\.?|doctorate|doctoral)\b", re.I),
}
_DEGREE_ANY = re.compile(r"\b(?:degree|diploma|bachelor'?s?|master'?s?|ph\.?d\.?|doctorate|b\.?sc\.?|m\.?sc\.?|mba|b\.?eng\.?)\b", re.I)
# Words that say little about a requirement on their own; a requirement is judged on the rest.
FILLER = {
    "ability", "strong", "excellent", "proven", "solid", "good", "great", "relevant", "demonstrated", "familiarity", "proficiency", "proficient",
    "hands-on", "hands", "plus", "bonus", "preferred", "required", "equivalent", "related", "similar", "etc", "environment", "environments",
    "knowledge", "understanding", "experience", "experienced", "skills", "skill", "work", "working", "ideally", "least", "minimum",
}
DEGREE_LABEL = {1: "a bachelor's degree", 2: "a master's degree", 3: "a doctorate"}


# --- reading the posting ---------------------------------------------------------------------------------------------------------

def description_hash(description: str) -> str:
    return hashlib.sha1((description or "").strip().encode("utf-8", "replace")).hexdigest()[:20]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", _BULLET.sub("", line)).strip(" \t-*:;")[:MAX_LINE]


def _is_heading(line: str) -> bool:
    text = line.strip()
    return bool(text) and len(text) <= 60 and not _BULLET.match(text) and (text.endswith(":") or bool(_REQ_HEADING.match(text.rstrip(":"))))


def _section_lines(text: str) -> list[str]:
    """The lines under a Requirements-style heading, until the next heading of another kind (Benefits, About us...)."""
    out: list[str] = []
    inside = False
    seen = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_heading(line):
            inside = bool(_REQ_HEADING.match(line.rstrip(":")))
            seen = 0
            continue
        if inside:
            seen += 1
            if seen > 25:
                inside = False
                continue
            cleaned = _clean_line(line)
            if len(cleaned) >= 8:
                out.append(cleaned)
    return out


def _years_in(line: str) -> int | None:
    found = [int(m.group(1)) for m in _YEARS.finditer(line)]
    return max(found) if found else None


def _degree_in(line: str) -> int | None:
    levels = [level for level, pattern in _DEGREE_WORDS.items() if pattern.search(line)]
    if levels:
        return min(levels)  # "Bachelor's or Master's" asks for the lower
    return 0 if _DEGREE_ANY.search(line) else None  # 0: a degree, level not said


def _requirement(text: str, kind: str = "line") -> dict:
    techs = list(techskills._found_in(text))
    return {
        "id": hashlib.sha1(text.lower().encode("utf-8", "replace")).hexdigest()[:10],
        "text": text, "kind": kind, "techs": techs, "years": _years_in(text), "degree": _degree_in(text),
    }


def extract_requirements(description: str) -> list[dict]:
    """What the posting asks for, as short lines: its requirement bullets, then any years or degree phrase and named technology not already in one."""
    description = (description or "").replace("\x00", "")
    if not description.strip():
        return []
    lines = _section_lines(description)
    if not lines:  # no heading: the bullets that name a tool, a number of years or a degree
        for raw in description.splitlines():
            if _BULLET.match(raw):
                cleaned = _clean_line(raw)
                if len(cleaned) >= 8 and (techskills._found_in(cleaned) or _years_in(cleaned) is not None or _degree_in(cleaned) is not None):
                    lines.append(cleaned)
    out: list[dict] = []
    seen: set[str] = set()

    def add(text: str, kind: str = "line"):
        req = _requirement(text, kind)
        if req["id"] not in seen and len(out) < MAX_REQUIREMENTS:
            seen.add(req["id"])
            out.append(req)

    for line in lines:
        add(line)
    flat = " ".join(out_["text"].lower() for out_ in out)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", description) if s.strip()]
    for sentence in sentences:  # a years or degree phrase that is not in a line already
        trimmed = sentence[:MAX_LINE]
        if (_years_in(trimmed) is not None or _degree_in(trimmed) is not None) and trimmed.lower() not in flat and len(trimmed) >= 12:
            if not any(trimmed.lower() in o["text"].lower() or o["text"].lower() in trimmed.lower() for o in out):
                add(_clean_line(trimmed), "years" if _years_in(trimmed) is not None else "degree")
    covered_techs = {t for o in out for t in o["techs"]}
    for name, _hot in sorted(techskills._found_in(description).items(), key=lambda kv: (not kv[1], kv[0].lower())):
        if name not in covered_techs:
            add(name, "tech")
    return out[:MAX_REQUIREMENTS]


# --- reading it with the person's own AI (optional) ---------------------------------------------------------------------------

AI_SYSTEM = assist.SAFETY + """

Task: list what the job posting inside <job_posting> asks of a candidate, as short requirement lines (skills, tools, years of experience, qualifications).
Copy or closely condense the posting's own words; add nothing the posting does not say. At most 12 lines, each under 160 characters.
Reply with {"requirements": ["...", "..."]}."""


def _norm_word(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _vocab(text: str) -> set[str]:
    return {_norm_word(t) for t in terms(text)}


def validate_ai_requirements(raw: dict, description: str) -> list[dict]:
    """Keep only lines whose substance is in the posting: an AI that adds a requirement the posting never mentions is ignored."""
    posting = _vocab(description)
    out: list[dict] = []
    for line in assist._strings(raw.get("requirements") if isinstance(raw, dict) else None, MAX_REQUIREMENTS * 2, 160):
        words = _vocab(line)
        if len(words) == 0 or len(words & posting) < ceil(0.7 * len(words)):
            continue
        if len(line) >= 4:
            out.append(_requirement(line))
        if len(out) >= MAX_REQUIREMENTS:
            break
    return out


def read_with_ai(app, config: SiteConfig, owner) -> list[dict]:
    """The requirements as the person's own AI reads them (cached per person and posting). Raises `assist.AssistError` in plain words."""
    assist.require_ai(config)
    if not (app.description or "").strip():
        raise assist.AssistError("Add the job description first, so there is something to read.")
    key = f"matchreq-ai:{owner.pk}:{description_hash(app.description)}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    raw = assist.ask(config, AI_SYSTEM, assist.data("job_posting", app.description, config.ai_max_input_chars), app, "match_card", owner)
    found = validate_ai_requirements(raw, app.description)
    if not found:
        raise assist.AssistError("The AI did not find any requirements in this posting that we could confirm. The list from the posting's own text is shown instead.")
    cache.set(key, found, CACHE_SECONDS)
    return found


def requirements_for(app, owner) -> tuple[list[dict], str]:
    """(requirements, method): the person's own AI reading if they asked for one before, else the free reading. Cached per description."""
    h = description_hash(app.description)
    ai_hit = cache.get(f"matchreq-ai:{owner.pk}:{h}")
    if ai_hit:
        return ai_hit, "ai"
    key = f"matchreq:{h}"
    hit = cache.get(key)
    if hit is None:
        hit = extract_requirements(app.description)
        cache.set(key, hit, CACHE_SECONDS)
    return hit, "keywords"


# --- the person's own material ------------------------------------------------------------------------------------------------

def _origin(source) -> dict:
    """Where a line of material is from, in the person's own words."""
    if source["key"] in ("profile-cv", "careerops:cv.md") or source["kind"] == "cv":
        return {"label": "from your CV", "title": source["title"], "kind": "cv"}
    if source["key"] == FACTS_KEY:
        return {"label": "from a fact you added", "title": source["title"], "kind": "fact"}
    return {"label": f"from your note '{source['title']}'", "title": source["title"], "kind": source["kind"]}


def material_for(owner, config: SiteConfig) -> list[dict]:
    """The person's enabled sources as {key, title, kind, lines}, the CV first. Only their own rows."""
    knowledge.sync_cv(config, owner)
    rows = KnowledgeSource.objects.filter(owner=owner, enabled=True).exclude(text="")
    out = []
    for s in rows:
        lines = [_clean_line(line) for line in s.text.splitlines()]
        out.append({"key": s.key or "", "title": s.title, "kind": s.kind, "lines": [x for x in lines if len(x) >= 3]})
    out.sort(key=lambda s: (_origin(s)["kind"] != "cv", s["title"].lower()))
    return out


def _snippet(line: str, around: str = "") -> str:
    line = line.strip()
    if len(line) <= SNIPPET:
        return line
    at = line.lower().find(around.lower()) if around else -1
    start = max(0, (at if at >= 0 else 0) - 40)
    chunk = line[start:start + SNIPPET].strip()
    return ("…" if start else "") + chunk + "…"


def _find(material: list[dict], test) -> tuple[dict, str] | None:
    for source in material:
        for line in source["lines"]:
            if test(line):
                return source, line
    return None


def _years_stated(line: str) -> int:
    found = [int(m.group(1)) for m in _YEARS.finditer(line)]
    return max(found) if found else 0


def _check_one(req: dict, material: list[dict]) -> dict:
    """{"state": "covered"|"gap", "source": origin|None, "snippet": str, "hint": str} for one requirement."""
    techs = req["techs"]
    hit = None
    parts_ok = True
    hint = ""
    if techs:
        for name in techs:  # any one of the tools named is enough ("Python or Go")
            pattern = re.compile(r"(?<![\w+#.])" + re.escape(name) + r"(?![\w+#])", re.I)
            hit = _find(material, pattern.search)
            if hit:
                break
        parts_ok = hit is not None
        if not parts_ok:
            hint = f"Your material does not mention {', '.join(techs[:3])}."
    if req["years"] is not None:
        need = req["years"]
        years_hit = _find(material, lambda line: _years_stated(line) >= need)
        if years_hit is None:
            parts_ok = False
            hint = hint or f"Your material does not say you have {need} years."
        elif hit is None:
            hit = years_hit
    if req["degree"] is not None:
        need_level = req["degree"]

        def has_degree(line: str) -> bool:
            if need_level == 0:
                return bool(_DEGREE_ANY.search(line))
            return any(level >= need_level and pattern.search(line) for level, pattern in _DEGREE_WORDS.items())

        degree_hit = _find(material, has_degree)
        if degree_hit is None:
            parts_ok = False
            hint = hint or f"Your material does not mention {DEGREE_LABEL.get(need_level, 'a degree')}."
        elif hit is None:
            hit = degree_hit
    if not techs and req["years"] is None and req["degree"] is None:  # a plain requirement: most of its own words must be in one line of the material
        wanted = [w for w in dict.fromkeys(_norm_word(t) for t in terms(req["text"])) if w not in FILLER][:8]
        if not wanted:
            return {"state": "gap", "source": None, "snippet": "", "hint": "We cannot tell what to look for in this one."}
        need = ceil(0.6 * len(wanted)) if len(wanted) > 1 else 1
        best = None
        for source in material:
            for line in source["lines"]:
                have = len(set(wanted) & _vocab(line))
                if have >= need and (best is None or have > best[0]):
                    best = (have, source, line)
        if best:
            hit = (best[1], best[2])
        else:
            parts_ok = False
            hint = "Nothing in your material says this yet."
    if parts_ok and hit:
        source, line = hit
        return {"state": "covered", "source": _origin(source), "snippet": _snippet(line, techs[0] if techs else ""), "hint": ""}
    return {"state": "gap", "source": None, "snippet": "", "hint": hint or "Nothing in your material says this yet."}


def card(app, config: SiteConfig, owner) -> dict:
    """The "How you match" card for one of the person's jobs."""
    description = (app.description or "").strip()
    base = {
        "job_id": app.pk, "excerpt": bool(app.description_is_excerpt), "can_ai": assist.has_ai(config), "requirements": [], "covered": 0, "total": 0,
        "summary": "", "has_material": False, "method": "keywords", "empty": "",
    }
    if not description:
        return {**base, "empty": "no_description", "summary": "Add the job description to see how you match. Open Edit details and paste it in."}
    reqs, method = requirements_for(app, owner)
    material = material_for(owner, config)
    has_material = any(s["lines"] for s in material)
    base.update(method=method, has_material=has_material)
    if not reqs:
        return {**base, "empty": "no_requirements", "summary": "We could not find a list of requirements in this posting. Your own AI can read it for you, or check the posting itself."}
    rows = []
    for req in reqs:
        res = _check_one(req, material) if has_material else {"state": "unchecked", "source": None, "snippet": "", "hint": ""}
        rows.append({"id": req["id"], "text": req["text"], "kind": req["kind"], **res})
    covered = sum(1 for r in rows if r["state"] == "covered")
    summary = (
        f"{covered} of {len(rows)} covered" if has_material
        else f"{len(rows)} requirement{'s' if len(rows) != 1 else ''} found. Add your CV in Profile to see which ones you cover."
    )
    return {**base, "requirements": rows, "covered": covered, "total": len(rows), "summary": summary, "empty": "" if has_material else "no_material"}


# --- "Add to my profile" ---------------------------------------------------------------------------------------------------

class FactError(Exception):
    """In plain words."""


def add_fact(owner, config: SiteConfig, text: str, job) -> dict:
    """Append one fact the person wrote to their own notes ("Facts I added from job matches"), where the matching, tailoring and fact-check read it.

    Only the text they typed is stored, under a label that says where it came from. Nothing is ever added without their words."""
    fact = re.sub(r"\s+", " ", (text or "").replace("\x00", "")).strip()
    if not fact:
        raise FactError("Write the fact in your own words first. It is only saved when you type it.")
    if len(fact) > MAX_FACT:
        raise FactError(f"Keep it under {MAX_FACT} characters: one short fact.")
    source = KnowledgeSource.objects.filter(owner=owner, key=FACTS_KEY).first()
    line = f"- {fact}"
    if source and line.lower() in source.text.lower():
        return {"added": False, "message": "That is already in your notes.", "source_id": source.pk}
    stamp = f"{timezone.localdate():%d %b %Y}"
    entry = f"{line} (added by you on {stamp} while looking at {job.role} at {job.company})"
    if source is None:
        from django.conf import settings

        if KnowledgeSource.objects.filter(owner=owner).count() >= settings.STILLOPEN_MAX_KNOWLEDGE:
            raise FactError(f"You have reached the limit of {settings.STILLOPEN_MAX_KNOWLEDGE} documents. Delete one first.")
        source = KnowledgeSource.objects.create(owner=owner, key=FACTS_KEY, title=FACTS_TITLE, kind="skills", text=entry)
    else:
        if len(source.text) + len(entry) > MAX_FACTS_CHARS:
            raise FactError("That notes list is full. Tidy it up in Your documents first.")
        source.text = f"{source.text.rstrip()}\n{entry}"
        source.save()
    knowledge.reindex_source(source, config)
    return {"added": True, "message": "Added to your notes. Your matches now use it.", "source_id": source.pk}
