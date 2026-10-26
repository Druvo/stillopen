"""Assemble a first CV from a short, free, guided Q&A -- no AI, nothing beyond what the person typed.

Lets a candidate who has never written a CV get one from a handful of structured fields instead of needing to
already have a document to paste. The result becomes a normal master CVVersion through the same path as
pasting a CV by hand (`cvversions.record_master`), so it gets the same immutable history, the same free RAG/
keyword matching, and the same export pipeline as any other CV -- no separate code path to keep in sync.
"""
import re

from tracker.models import SiteConfig, UserProfile
from tracker.services import knowledge
from tracker.services.cvversions import CVError, record_master


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _bullets(items: list[str]) -> list[str]:
    return [f"- {_clean(i)}" for i in items if _clean(i)]


def assemble_markdown(data: dict) -> str:
    """Build a plain Markdown CV from structured Q&A answers. A section with nothing in it is left out
    entirely -- there is no invented filler text for an empty field."""
    name = _clean(data.get("full_name"))
    if not name:
        raise CVError("Add your name first.")
    lines = [f"# {name}"]

    contact = [_clean(c) for c in (data.get("phone"), data.get("email"), data.get("location")) if _clean(c)]
    contact += [_clean(link) for link in (data.get("links") or []) if _clean(link)]
    if contact:
        lines += ["", " | ".join(contact)]

    summary = _clean(data.get("summary"))
    if summary:
        lines += ["", "## Summary", "", summary]

    skills = [_clean(s) for s in (data.get("skills") or []) if _clean(s)]
    if skills:
        lines += ["", "## Skills", "", ", ".join(skills)]

    experience = [e for e in (data.get("experience") or []) if _clean(e.get("company")) or _clean(e.get("role"))]
    if experience:
        lines += ["", "## Experience"]
        for job in experience:
            header = " — ".join(x for x in (_clean(job.get("role")), _clean(job.get("company"))) if x)
            lines += ["", f"**{header}**"]
            dates = " - ".join(x for x in (_clean(job.get("start")), _clean(job.get("end"))) if x)
            if dates:
                lines.append(dates)
            lines += _bullets(job.get("bullets") or [])

    education = [e for e in (data.get("education") or []) if _clean(e.get("school")) or _clean(e.get("degree"))]
    if education:
        lines += ["", "## Education"]
        for ed in education:
            header = " — ".join(x for x in (_clean(ed.get("degree")), _clean(ed.get("school"))) if x)
            dates = " - ".join(x for x in (_clean(ed.get("start")), _clean(ed.get("end"))) if x)
            lines.append(f"**{header}**" + (f" ({dates})" if dates else ""))

    projects = [p for p in (data.get("projects") or []) if _clean(p.get("name"))]
    if projects:
        lines += ["", "## Projects"]
        for p in projects:
            lines += ["", f"**{_clean(p.get('name'))}**"]
            description = _clean(p.get("description"))
            if description:
                lines.append(description)

    certifications = [_clean(c) for c in (data.get("certifications") or []) if _clean(c)]
    if certifications:
        lines += ["", "## Certifications", ""] + _bullets(certifications)

    return "\n".join(lines).strip()


def build_and_save(owner, data: dict):
    """Assemble the Markdown, make it the person's profile CV, and record it as their next master version --
    the same path pasting a CV by hand takes, so matching, RAG and tailoring all pick it up at once."""
    markdown = assemble_markdown(data)
    UserProfile.objects.filter(user=owner).update(profile_cv=markdown)
    version = record_master(owner, markdown, label="Built from questions")
    knowledge.sync_cv(SiteConfig.for_user(owner), owner)
    return version
