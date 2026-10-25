"""Keyless regional job searches that publish an open API, each asked with one person's own target roles.

Checked live and against their own published terms when added (2026-10):
- JobTech / Platsbanken (Sweden): the Swedish Public Employment Service's JobSearch API; open data, no key.
- Get on Board (Latin America tech jobs): its public REST API reference documents the job search without a key.

Both are searches (like Jooble), so the answer depends on whose roles were asked for. Neither is allowed on the public
board (`seed_sources.PUBLIC_OK_CONNECTORS` is an allow-list and they are not in it). Every URL goes through `netguard.safe_get`.
"""
import html
import json
from datetime import datetime, timezone
from urllib.parse import quote

from tracker.services.jobtext import html_to_text
from tracker.services.netguard import FetchError, safe_get

ROLES_PER_PLACE = 3


def blurb(raw_html: str, limit: int = 2000) -> str:
    """Plain text from an HTML or plain description, trimmed (escaped markup is undone first)."""
    if not raw_html:
        return ""
    if "&lt;" in raw_html:
        raw_html = html.unescape(raw_html)
    return html_to_text(raw_html)[:limit]


def role_list(roles, limit: int = ROLES_PER_PLACE) -> list[str]:
    return [r.strip() for r in (roles or []) if r and r.strip()][:limit]


def _json(url: str) -> dict:
    resp = safe_get(url, timeout=20, headers={"Accept": "application/json"})
    if resp.status_code == 429:
        raise FetchError("The service's free limit was reached; it is tried again on a later search.")
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    try:
        return resp.json() or {}
    except ValueError as exc:
        raise FetchError("The service sent something unexpected.") from exc


# ---- Sweden: JobTech Platsbanken -------------------------------------------------------------------------------------------

JOBTECH_PLACES = {"se": "Sweden"}


def fetch_jobtech(token: str, roles: list[str] | None = None) -> list[dict]:
    """https://jobsearch.api.jobtechdev.se/search?q=<role>&limit=100. `token`: se."""
    place = JOBTECH_PLACES.get((token or "").lower())
    if place is None:
        raise FetchError("Unknown JobTech place.")
    out, seen = [], set()
    for role in role_list(roles):
        data = _json(f"https://jobsearch.api.jobtechdev.se/search?q={quote(role, safe='')}&limit=100")
        for hit in data.get("hits", []):
            link = hit.get("webpage_url") or ""
            if not link or link in seen:
                continue
            seen.add(link)
            address = hit.get("workplace_address") or {}
            city = (address.get("municipality") or address.get("city") or "").strip()
            out.append({
                "title": (hit.get("headline") or "").strip(), "url": link,
                "location": f"{city}, {place}" if city else place,
                "company": ((hit.get("employer") or {}).get("name") or "").strip(),
                "description": blurb((hit.get("description") or {}).get("text", "")),
                "posted": (hit.get("publication_date") or "")[:10],
            })
    return out


# ---- Latin America: Get on Board ---------------------------------------------------------------------------------------------

GETONBRD_PLACES = {"latam": "Latin America"}


def fetch_getonbrd(token: str, roles: list[str] | None = None) -> list[dict]:
    """https://www.getonbrd.com/api/v0/search/jobs?query=<role>&expand=["company"]. `token`: latam."""
    if (token or "").lower() not in GETONBRD_PLACES:
        raise FetchError("Unknown Get on Board place.")
    out, seen = [], set()
    expand = quote(json.dumps(["company"]), safe="")
    for role in role_list(roles):
        data = _json(f"https://www.getonbrd.com/api/v0/search/jobs?query={quote(role, safe='')}&per_page=50&expand={expand}")
        for job in data.get("data", []):
            attrs = job.get("attributes") or {}
            link = (job.get("links") or {}).get("public_url") or ""
            if not link or link in seen:
                continue
            seen.add(link)
            countries = [c for c in (attrs.get("countries") or []) if isinstance(c, str) and c.strip()]
            real = [c for c in countries if c.lower() != "remote"]
            if real:
                where = ", ".join(real) + (" (remote)" if attrs.get("remote") else "")
            else:
                where = "Remote"
            company = (((attrs.get("company") or {}).get("data") or {}).get("attributes") or {}).get("name", "")
            low, high = attrs.get("min_salary"), attrs.get("max_salary")
            salary = ""
            if low or high:
                salary = f"{int(low or high):,}" + (f" - {int(high):,}" if high and high != low else "") + " USD/month"
            published = attrs.get("published_at")
            posted = ""
            if isinstance(published, (int, float)):
                posted = datetime.fromtimestamp(published, tz=timezone.utc).date().isoformat()
            out.append({
                "title": (attrs.get("title") or "").strip(), "url": link, "location": where, "company": str(company).strip(),
                "description": blurb(" ".join(str(attrs.get(k) or "") for k in ("projects", "functions", "description"))),
                "salary": salary, "posted": posted,
            })
    return out
