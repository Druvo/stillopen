"""Search configured job boards for postings matching your target roles.

Zero-token: every connector here is a plain public JSON or RSS endpoint -- Greenhouse, Lever, Ashby,
SmartRecruiters and Recruitee for a single company's own board; RemoteOK, We Work Remotely and Himalayas for a
multi-employer aggregator. Finding a posting costs one HTTP GET per enabled JobSource, no AI call. Scoring/
tailoring a posting once it's in your tracker still goes through the normal (optional, BYOK) AI path -- this
module only discovers and records it.

Checked and NOT added: Workable's public job-board API returned an empty result for every real company tried
(Dashlane, Pipedrive, Skyscanner, Typeform, Babbel...) -- looks deprecated/sunset rather than unreachable, so
it isn't wired in without a confirmed-working account to verify against.

Deliberately NOT a connector here: LinkedIn (scraping it violates its Terms of Service and its anti-bot
measures are the kind this project won't try to defeat -- see AGENTS.md-equivalent discipline in CLAUDE.md;
paste a LinkedIn URL into "Add job" instead, which fetches that one page you asked for, not a search) and any
board with no public API or feed that would require a headless browser to read (bdjobs.com is a client-side
app with no server-rendered listings and no documented API -- out of scope for this zero-token module; a
Playwright-based scanner the way career-ops' own scan-interamt.mjs handles an equivalent case is a different,
heavier kind of connector and isn't built here).

A posting is matched against your own UserProfile.target_roles (simple case-insensitive phrase containment,
the same zero-token approach career-ops' own title_filter uses) before anything is saved, and a posting whose
URL you already track is skipped as a duplicate rather than re-added. A posting whose title misses every
target-role phrase can still be added on skill overlap: the candidate's own most-repeated CV/knowledge terms
(services/text.terms, same tokenizer as the free keyword-match fallback) are compared against the posting's
title plus whatever description text its connector already returns (free -- several connectors include it in
the same list response, no extra request), and STILLOPEN_SKILL_MATCH_MIN_OVERLAP or more shared terms is
enough. A skill-matched addition gets a plain Event note naming the overlap, and the dashboard shows a
"Skill match" badge, so it's always clear why a role with no matching title showed up.

Every posting fetched -- matched or not -- is also recorded as a `Posting` sighting (see record_sighting/
repost_signal below), shared across everyone watching that source. This is what a repost/ghost-job pattern is
read from later: a company re-listing the same role under a new URL shows up as several Postings sharing one
title_key at the same source, seen across more than one calendar day. Two concurrent openings posted the same
day are not flagged -- same discipline as career-ops' own detect-reposts.mjs (2+ distinct URLs, 2+ distinct
scan dates). This is an observation, never a verdict: a real company can legitimately re-post a role.
"""
import hashlib
import html
import re
import threading
import time
from collections import Counter
from datetime import timedelta

from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from tracker.models import (
    Application, Event, JobSource, Posting, PostingSighting, ScanLogEntry, ScanRun, SiteConfig, Status, UserProfile,
)
from tracker.services import ai, fit, geo, knowledge
from tracker.services.jobtext import html_to_text
from tracker.services.netguard import FetchError, safe_get
from tracker.services.text import terms as _terms

STALE_AFTER = timedelta(minutes=20)
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SKILL_TERMS_KEPT = 80  # the candidate's own most-repeated skill-ish terms, same idea as ai.keyword_match's JD side


def _roles(owner) -> list[str]:
    profile = UserProfile.for_user(owner)
    return [r.strip().lower() for r in profile.target_roles.splitlines() if r.strip()]


def _skill_terms(owner) -> set[str]:
    """The candidate's own most-repeated skill-ish terms (from their CV + knowledge docs), used to catch a
    posting whose title doesn't literally contain one of their target-role phrases but whose content shares
    real skill overlap -- e.g. target_roles="Backend Engineer" missing a posting titled "C# Developer" that
    the candidate's own CV strongly matches. Free, zero-token, the same tokenizer as the keyword-match
    fallback (services/text.terms). Empty for a candidate with no CV/knowledge text yet -- skill matching is
    then simply a no-op and title matching alone still applies, no regression."""
    config = SiteConfig.for_user(owner)
    text_blob = knowledge.all_candidate_text(config, owner)
    if not text_blob.strip():
        return set()
    return {w for w, _ in Counter(_terms(text_blob)).most_common(SKILL_TERMS_KEPT)}


def _skill_overlap(text_blob: str, skill_terms: set[str]) -> set[str]:
    if not text_blob or not skill_terms:
        return set()
    return set(_terms(text_blob)) & skill_terms


def title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())[:300]


def record_sighting(source: JobSource, title: str, url: str, location: str, company: str | None = None, seen_date=None) -> Posting:
    """Upsert the Posting for (source, url) and mark it seen today (or `seen_date`, for tests).

    `company` defaults to the source's own name (correct for a single-company connector). An aggregator
    connector passes the posting's actual employer explicitly, since it varies per posting -- the key is
    derived from company+title together so two different real employers on one aggregator are never grouped
    as if one of them were reposting the other's role."""
    company = (company or source.name).strip()
    seen_date = seen_date or timezone.localdate()
    posting, _ = Posting.objects.update_or_create(
        source=source, url=url[:600],
        defaults={
            "title": title[:300], "company": company[:160],
            "title_key": title_key(f"{company} :: {title}"), "location": (location or "")[:160],
        },
    )
    PostingSighting.objects.get_or_create(posting=posting, seen_date=seen_date)
    return posting


_REMOTE_WORDS = re.compile(r"\bremote\b|\banywhere\b|\bworldwide\b|work from home|\bdistributed\b", re.I)
EXCERPT_CHARS = 400


def excerpt_of(text: str) -> str:
    """The first few lines of a posting for the public board, cut at a word: enough to recognise the job, never the whole text
    (the full posting stays with the employer, one click away)."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)  # belt and braces: never let markup reach a public page as text
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[:EXCERPT_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."


_TERM_HINT = re.compile(r"sponsor|visa|work permit|right to work|relocat|authori[sz]ation|full[- ]time|part[- ]time|permanent|contract|fixed[- ]term|freelance|intern", re.I)


def _terms_of(title: str, description: str) -> dict:
    """Visa, relocation, contract and level facts for one posting, as Posting fields. The cheap hint test first keeps this
    off the regexes for the many postings that say none of it (a first search reads ~20,000)."""
    raw = (description or "")[:12000]
    if not (_TERM_HINT.search(raw) or _TERM_HINT.search(title)):
        found = geo.detect_terms(title, "")
    else:
        text = re.sub(r"<[^>]+>", " ", html.unescape(raw))
        found = geo.detect_terms(title, re.sub(r"\s+", " ", text)[:6000])
    return {name: found.get(name, "") for name in ("sponsorship", "relocation", "employment_type", "seniority")}


def record_sightings(source: JobSource, postings: list[dict], seen_date=None) -> None:
    """record_sighting for a whole list of postings from one source in a handful of queries instead of two per
    posting (a first search reads ~20,000 openings). Same result: the Posting is created or refreshed and marked seen today."""
    seen_date = seen_date or timezone.localdate()
    rows, urls = [], set()
    for p in postings:
        url = p["url"][:600]
        if url in urls:
            continue
        urls.add(url)
        company = (p.get("company") or source.name).strip()
        location = (p.get("location") or "")[:160]
        codes = geo.location_codes(location)
        rows.append(Posting(
            source=source, url=url, title=p["title"][:300], company=company[:160],
            title_key=title_key(f"{company} :: {p['title']}"), location=location,
            country=next(iter(codes)) if len(codes) == 1 else "",
            remote=bool(_REMOTE_WORDS.search(f"{location} {p['title']}")),
            excerpt=excerpt_of(p.get("description", "")),
            **_terms_of(p["title"], p.get("description", "")),
        ))
    for i in range(0, len(rows), 500):
        Posting.objects.bulk_create(
            rows[i:i + 500], update_conflicts=True, unique_fields=["source", "url"],
            update_fields=["title", "company", "title_key", "location", "country", "remote", "excerpt",
                           "sponsorship", "relocation", "employment_type", "seniority", "last_seen_at"],
        )
    ids = {}
    ordered = list(urls)
    for i in range(0, len(ordered), 500):
        ids.update(Posting.objects.filter(source=source, url__in=ordered[i:i + 500]).values_list("url", "pk"))
    PostingSighting.objects.bulk_create(
        [PostingSighting(posting_id=pk, seen_date=seen_date) for pk in ids.values()], batch_size=500, ignore_conflicts=True,
    )


def repost_signal(posting: Posting) -> dict | None:
    """None if `posting` shows no repost pattern; otherwise the evidence -- never a verdict on why."""
    siblings = Posting.objects.filter(source_id=posting.source_id, title_key=posting.title_key)
    distinct_urls = siblings.count()
    dates = set(PostingSighting.objects.filter(posting__in=siblings).values_list("seen_date", flat=True))
    if distinct_urls < 2 or len(dates) < 2:
        return None
    return {
        "distinct_urls": distinct_urls,
        "distinct_dates": len(dates),
        "first_seen": siblings.order_by("first_seen_at").first().first_seen_at,
        "last_seen": siblings.order_by("-last_seen_at").first().last_seen_at,
    }


_FILLER = {
    "senior", "sr", "junior", "jr", "lead", "staff", "principal", "head", "chief", "associate", "intern", "the", "a", "an",
    "and", "of", "for", "in", "at", "i", "ii", "iii", "iv", "remote", "hybrid", "new", "grad",
}
_SYNONYMS = {"developer": "engineer", "dev": "engineer", "programmer": "engineer", "swe": "engineer", "sde": "engineer", "engineers": "engineer", "developers": "engineer"}
_COMPOUNDS = [("back-end", "backend"), ("back end", "backend"), ("front-end", "frontend"), ("front end", "frontend"),
              ("full-stack", "fullstack"), ("full stack", "fullstack"), ("dev ops", "devops"), ("machine learning", "ml")]
_WORD = re.compile(r"[a-z0-9+#.]+")


def _normalise_title(text: str) -> set[str]:
    text = (text or "").lower()
    for old, new in _COMPOUNDS:
        text = text.replace(old, new)
    return {_SYNONYMS.get(w.strip("."), w.strip(".")) for w in _WORD.findall(text) if w.strip(".")}


def _matches(title: str, roles: list[str]) -> bool:
    """A posting title fits a target role when the role's own words are all in the title, in any order:
    "Backend Engineer" matches "Senior Software Engineer, Back-end" and "Backend Developer". Seniority words
    are ignored here (the fit check handles seniority). The role as a plain phrase still matches too."""
    if not roles or not title:
        return False
    t = title.lower()
    words = _normalise_title(title)
    for role in roles:
        if role in t:
            return True
        core = _normalise_title(role) - _FILLER
        if core and core <= words:
            return True
    return False


def _tidy_place(text: str) -> str:
    """'Beijing, , China' (an empty region in the middle) becomes 'Beijing, China'."""
    return ", ".join(part.strip() for part in (text or "").split(",") if part.strip())


def _blurb(raw_html: str, limit: int = 2000) -> str:
    """Plain text from an HTML description field, trimmed. Some sources (Greenhouse) send their HTML escaped (&lt;p&gt;), so that
    is undone first, otherwise the tags would survive as visible text and pollute the words used for scoring. Used for skill
    matching, the saved job text and the public excerpt, so a couple of KB is plenty and keeps per-posting parsing cheap."""
    if not raw_html:
        return ""
    if "&lt;" in raw_html:
        raw_html = html.unescape(raw_html)
    return html_to_text(raw_html)[:limit]


def fetch_greenhouse(token: str) -> list[dict]:
    # content=true costs nothing extra (still one request) and gives the posting's own description text,
    # which is what makes skill-based matching possible beyond the title alone.
    resp = safe_get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "description": _blurb(j.get("content", "")),
        })
    return out


def fetch_lever(token: str) -> list[dict]:
    resp = safe_get(f"https://api.lever.co/v0/postings/{token}?mode=json", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json():
        cats = j.get("categories") or {}
        out.append({
            "title": j.get("text", ""),
            "url": j.get("hostedUrl", ""),
            "location": cats.get("location", ""),
            "description": _blurb(j.get("descriptionPlain") or j.get("description", "")),
        })
    return out


def fetch_ashby(token: str) -> list[dict]:
    resp = safe_get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "location": j.get("location", ""),
            "description": _blurb(j.get("descriptionHtml") or j.get("description", "")),
        })
    return out


def fetch_smartrecruiters(token: str) -> list[dict]:
    # The list endpoint has no description field (SmartRecruiters only returns it from a per-posting detail
    # call) -- title-only matching, same as before, for this one connector.
    out, offset = [], 0
    while True:  # 100 a page; large employers (Grab, Delivery Hero) have several pages
        resp = safe_get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset={offset}", timeout=20)
        if resp.status_code != 200:
            if offset == 0:
                raise FetchError(f"HTTP {resp.status_code}")
            break
        data = resp.json()
        page = data.get("content", [])
        for j in page:
            posting_id = j.get("id", "")
            out.append({
                "title": j.get("name", ""),
                "url": f"https://jobs.smartrecruiters.com/{token}/{posting_id}" if posting_id else "",
                "location": _tidy_place((j.get("location") or {}).get("fullLocation", "")),
            })
        offset += len(page)
        if not page or offset >= min(int(data.get("totalFound") or 0), SMARTRECRUITERS_MAX):
            break
    return out


def fetch_recruitee(token: str) -> list[dict]:
    resp = safe_get(f"https://{token}.recruitee.com/api/offers/", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("offers", []):
        location = ", ".join(x for x in (j.get("city"), j.get("country")) if x) or ("Remote" if j.get("remote") else "")
        out.append({
            "title": j.get("title", ""),
            "url": j.get("careers_apply_url") or j.get("careers_url") or "",
            "location": location,
            "description": _blurb(j.get("description", "")),
        })
    return out


def fetch_remoteok(token: str) -> list[dict]:
    """RemoteOK's public API (https://remoteok.com/api, documented in its own `legal` field). `token` is an
    optional tag filter (e.g. 'dev'); 'all' or blank fetches unfiltered. Aggregator: company varies per posting."""
    url = "https://remoteok.com/api" if token in ("", "all") else f"https://remoteok.com/api?tags={token}"
    resp = safe_get(url, timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json():
        if not j.get("id"):
            continue  # first element is RemoteOK's own legal/attribution notice, not a job
        out.append({
            "title": j.get("position", ""),
            "url": j.get("url", ""),
            "location": j.get("location") or "Remote",
            "company": j.get("company", ""),
            "description": _blurb(j.get("description", "")),
        })
    return out


def fetch_weworkremotely(token: str) -> list[dict]:
    """We Work Remotely's public RSS feeds. `token` is an optional category slug (e.g.
    'remote-full-stack-programming-jobs'); 'all' or blank fetches the combined feed of every category.
    Aggregator: company varies per posting, and WWR's own <title> is 'Company: Role' together."""
    import xml.etree.ElementTree as ET

    url = (
        "https://weworkremotely.com/remote-jobs.rss"
        if token in ("", "all")
        else f"https://weworkremotely.com/categories/{token}.rss"
    )
    resp = safe_get(url, timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        raise FetchError(f"Could not parse feed: {exc}") from exc
    out = []
    for item in root.findall(".//item"):
        raw = (item.findtext("title") or "").strip()
        company, sep, role = raw.partition(": ")
        if not sep:  # no "Company: Role" split found -- treat the whole thing as the title
            company, role = "", raw
        out.append({
            "title": role.strip(),
            "url": (item.findtext("link") or "").strip(),
            "location": (item.findtext("region") or "").strip(),
            "company": company.strip(),
            "description": _blurb(item.findtext("description") or ""),
        })
    return out


def fetch_himalayas(token: str) -> list[dict]:
    """Himalayas' public API (https://himalayas.app/jobs/api, documented in its own `comments` field). No
    working server-side keyword/category filter was found to exist for it, so `token` is ignored and this
    always fetches the newest page. Aggregator: company varies per posting."""
    resp = safe_get("https://himalayas.app/jobs/api?limit=100", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("jobs", []):
        restrictions = j.get("locationRestrictions") or []
        out.append({
            "title": j.get("title", ""),
            "url": j.get("applicationLink", ""),
            "location": ", ".join(restrictions) if restrictions else "Remote",
            "company": j.get("companyName", ""),
            "description": _blurb(j.get("description", "")),
        })
    return out


def fetch_remotive(token: str) -> list[dict]:
    """Remotive's public API (https://remotive.com/api/remote-jobs). `token` is ignored. Aggregator."""
    resp = safe_get("https://remotive.com/api/remote-jobs", timeout=30)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    return [{
        "title": j.get("title", ""), "url": j.get("url", ""),
        "location": j.get("candidate_required_location") or "Remote",
        "company": j.get("company_name", ""), "description": _blurb(j.get("description", "")),
    } for j in resp.json().get("jobs", [])]


def fetch_arbeitnow(token: str) -> list[dict]:
    """Arbeitnow's public job-board API (https://www.arbeitnow.com/api/job-board-api). Mostly Germany and
    visa-sponsored roles in Europe. `token` is ignored. Aggregator."""
    resp = safe_get("https://www.arbeitnow.com/api/job-board-api", timeout=30)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("data", []):
        place = (j.get("location") or "").strip()
        out.append({
            "title": j.get("title", ""), "url": j.get("url", ""),
            "location": f"{place} (remote)" if j.get("remote") and place else ("Remote" if j.get("remote") else place),
            "company": j.get("company_name", ""), "description": _blurb(html.unescape(j.get("description", ""))),
        })
    return out


def fetch_jobicy(token: str) -> list[dict]:
    """Jobicy's public remote-jobs API (https://jobicy.com/api/v2/remote-jobs). `token` is ignored. Aggregator."""
    resp = safe_get("https://jobicy.com/api/v2/remote-jobs?count=100", timeout=30)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    return [{
        "title": j.get("jobTitle", ""), "url": j.get("url", ""),
        "location": f"Remote ({j['jobGeo']})" if j.get("jobGeo") else "Remote",
        "company": j.get("companyName", ""), "description": _blurb(j.get("jobDescription") or j.get("jobExcerpt", "")),
    } for j in resp.json().get("jobs", [])]


def fetch_workingnomads(token: str) -> list[dict]:
    """Working Nomads' public feed (https://www.workingnomads.com/api/exposed_jobs/). `token` is ignored. Aggregator."""
    resp = safe_get("https://www.workingnomads.com/api/exposed_jobs/", timeout=30)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    return [{
        "title": j.get("title", ""), "url": j.get("url", ""), "location": j.get("location") or "Remote",
        "company": j.get("company_name", ""), "description": _blurb(j.get("description", "")),
    } for j in resp.json()]


def fetch_themuse(token: str) -> list[dict]:
    """The Muse's public jobs API (https://www.themuse.com/api/public/jobs), first few pages. `token` is ignored. Aggregator."""
    out, pages = [], 1
    page = 1
    while page <= min(pages, 5):
        resp = safe_get(f"https://www.themuse.com/api/public/jobs?page={page}", timeout=30)
        if resp.status_code != 200:
            if page == 1:
                raise FetchError(f"HTTP {resp.status_code}")
            break
        data = resp.json()
        pages = int(data.get("page_count") or 1)
        for j in data.get("results", []):
            places = ", ".join(l.get("name", "") for l in j.get("locations", []) if l.get("name"))
            out.append({
                "title": j.get("name", ""), "url": (j.get("refs") or {}).get("landing_page", ""),
                "location": places or "Remote", "company": (j.get("company") or {}).get("name", ""),
                "description": _blurb(j.get("contents", "")),
            })
        page += 1
    return out


SMARTRECRUITERS_MAX = 500  # most postings read from one employer


JOOBLE_PLACES = {
    "bd": "Bangladesh", "my": "Malaysia", "ae": "United Arab Emirates", "sa": "Saudi Arabia",
    "qa": "Qatar", "kw": "Kuwait", "bh": "Bahrain", "om": "Oman",
}
JOOBLE_ROLES_PER_PLACE = 3
_TAG = re.compile(r"<[^>]+>")


def fetch_jooble(token: str, roles: list[str] | None = None, key: str = "") -> list[dict]:
    """Jooble's partner search API (POST https://jooble.org/api/<key>, JSON {keywords, location, page}). Unlike a company
    board this is a search, so it is asked for one person's own target roles in one country (`token`: bd, my, ae...).
    Needs the site's free Jooble key; no key or no roles means nothing to ask. Aggregator: company varies per posting.
    The key is part of the URL, so it is never put in an error message or a log line."""
    place = JOOBLE_PLACES.get((token or "").lower())
    if place is None:
        raise FetchError("Unknown Jooble place.")
    if not key or not roles:
        return []
    from tracker.services.netguard import check_public_url
    import requests

    url = f"https://jooble.org/api/{key}"
    check_public_url("https://jooble.org/")
    out, seen = [], set()
    for role in roles[:JOOBLE_ROLES_PER_PLACE]:
        try:
            resp = requests.post(url, json={"keywords": role, "location": place, "page": 1}, timeout=20, allow_redirects=False,
                                 headers={"User-Agent": "StillOpen/1.0"})
        except requests.RequestException as exc:
            raise FetchError(f"Request failed: {exc.__class__.__name__}") from exc
        if resp.status_code in (401, 403, 404):
            raise FetchError("Jooble did not accept the key. Check it in Site configuration.")
        if resp.status_code != 200:
            raise FetchError(f"HTTP {resp.status_code}")
        for j in (resp.json() or {}).get("jobs", []):
            link = j.get("link") or ""
            if not link or link in seen:
                continue
            seen.add(link)
            where = (j.get("location") or "").strip()
            if place.lower() not in where.lower():
                where = f"{where}, {place}" if where else place
            out.append({
                "title": _TAG.sub("", j.get("title", "")).strip(), "url": link, "location": where,
                "company": (j.get("company") or "").strip(), "description": _blurb(j.get("snippet", "")),
            })
    return out


def _fetch(connector: str, token: str) -> list[dict]:
    # Resolved by name against this module's own namespace (not a dict built at import time) so that
    # mock.patch("tracker.services.scan.fetch_greenhouse", ...) in tests reaches the call that's actually made.
    fetcher = globals().get(f"fetch_{connector}")
    if fetcher is None:
        raise FetchError(f"Unknown connector: {connector}")
    return fetcher(token)


def _existing_urls(owner) -> set[str]:
    return set(Application.objects.filter(owner=owner).exclude(url="").values_list("url", flat=True))


def _job_key(company: str, title: str) -> tuple[str, str]:
    return (re.sub(r"\W+", " ", (company or "").lower()).strip(), re.sub(r"\W+", " ", (title or "").lower()).strip())


def _existing_job_keys(owner) -> dict[tuple[str, str], set]:
    """Company+title of everything the person already tracks, with the source each came from (None: added by hand).
    The same role at one company in several cities is several postings on one source, so only a copy turning up on
    a DIFFERENT source (the same job on two job sites) counts as a duplicate."""
    keys: dict[tuple[str, str], set] = {}
    for company, role, source_id in Application.objects.filter(owner=owner).values_list("company", "role", "posting__source_id"):
        keys.setdefault(_job_key(company, role), set()).add(source_id)
    return keys


def _triple(company: str, title: str, location: str) -> tuple[str, str, str]:
    return _job_key(company, title) + (re.sub(r"\W+", " ", (location or "").lower()).strip(),)


def _existing_triples(owner) -> set[tuple[str, str, str]]:
    """Company + title + place of everything tracked. Big employers post the same role many times over (one per team,
    each with its own link); one of them is enough on a dashboard."""
    return {_triple(c, r, loc) for c, r, loc in Application.objects.filter(owner=owner).values_list("company", "role", "location_text")}


def _is_cross_source_duplicate(existing_jobs: dict, company: str, title: str, source) -> bool:
    sources = existing_jobs.get(_job_key(company, title))
    return sources is not None and source.pk not in sources


def _fetch_cached(source: JobSource, roles: list[str] | None = None, jooble_key: str = "") -> list[dict]:
    """One read of a source's public list is shared by every person's search for a while, so a hundred people
    searching never means a hundred requests to the same company (and public feeds with a fair-use limit stay happy)."""
    seconds = settings.STILLOPEN_SCAN_CACHE_SECONDS
    key = f"scan-source:{source.connector}:{source.board_token}"
    if source.connector == "jooble":  # a search, not a list: the answer depends on whose roles were asked for
        key += ":" + hashlib.md5("|".join(sorted((roles or [])[:JOOBLE_ROLES_PER_PLACE])).encode()).hexdigest()[:16]
    if seconds > 0:
        hit = cache.get(key)
        if hit is not None:
            return hit
    if not TOKEN_RE.match(source.board_token):
        raise FetchError("Invalid board token.")
    if source.connector == "jooble":
        postings = fetch_jooble(source.board_token, roles, jooble_key)
    else:
        postings = _fetch(source.connector, source.board_token)
    if seconds > 0:
        cache.set(key, postings, timeout=seconds)
    return postings


def searchable_sources(owner):
    """The enabled sources a person's search can really use. Jooble sources need the site's key and the person's roles."""
    qs = JobSource.for_user(owner, enabled=True)
    if not SiteConfig.load().effective_jooble_key or not _roles(owner):
        qs = qs.exclude(connector="jooble")
    return qs


GENERIC_MIN_CORPUS = 200


def _read_corpus(fetched: dict, skill_terms: set[str]):
    """One pass over every posting just read, tokenizing each ONCE. Returns how many postings there were, how many contain
    each word, and for each posting (by id) the person's skill words it contains and how many distinct words it has. The
    rest of the search reuses that instead of tokenizing the same text again."""
    total, counts, memo = 0, Counter(), {}
    for postings in fetched.values():
        if isinstance(postings, Exception):
            continue
        for p in postings:
            total += 1
            words = set(_terms(f"{p.get('title', '')} {p.get('description', '')}"))
            counts.update(words)
            memo[id(p)] = (frozenset(words & skill_terms), len(words))
    return total, counts, memo


def _common_from(total: int, counts: Counter, share: float) -> set[str]:
    if total < GENERIC_MIN_CORPUS:  # too few postings for "common" to mean anything
        return set()
    return {term for term, n in counts.items() if n / total > share}


def _common_terms(fetched: dict, share: float, only: set[str] | None = None) -> set[str]:
    """Words so common across everything just read that they say nothing about any one job ("software", "systems",
    "build", "engineering"). Measured on the postings themselves, so it adapts to whatever the sources hold."""
    total, counts, _ = _read_corpus(fetched, set())
    common = _common_from(total, counts, share)
    return common & only if only is not None else common


def _generic_terms(fetched: dict, skill_terms: set[str], share: float) -> set[str]:
    """Of the person's own skill words, the ones that are generic filler across everything just read."""
    return _common_terms(fetched, share, only=skill_terms) if skill_terms else set()


def _prefetch_staged(sources: list[JobSource], roles: list[str] | None = None, jooble_key: str = "", on_progress=None, first_wait: float | None = None):
    """Read every source at once (they are different hosts, so this is polite and far faster than one by one).

    Returns (answers, finish). `answers` maps source id to its postings (or to the exception that stopped it) for every
    source that replied within `first_wait` seconds, so a search can start with the fast majority. `finish()` then waits
    for the slow ones, up to the overall deadline, and returns the complete map; a host still silent by then is recorded as
    "took too long" and its request carries on in the background, landing in the shared cache for the next search."""
    def one(source):
        try:
            return source.pk, _fetch_cached(source, roles, jooble_key)
        except Exception as exc:  # noqa: BLE001 - recorded on that source's log entry; the others carry on
            return source.pk, exc
    pool = ThreadPoolExecutor(max_workers=max(1, settings.STILLOPEN_SCAN_FETCH_THREADS))
    futures = {pool.submit(one, source): source for source in sources}
    results: dict = {}
    started = time.monotonic()
    deadline = settings.STILLOPEN_SCAN_DEADLINE_SECONDS

    def collect(timeout: float) -> None:
        waiting = [f for f in futures if futures[f].pk not in results]
        if not waiting:
            return
        try:
            for future in as_completed(waiting, timeout=max(0.0, timeout)):
                pk, value = future.result()
                results[pk] = value
                if on_progress:
                    on_progress(len(results))  # the person watches a counter move instead of a dead "0/118"
        except FuturesTimeout:
            pass

    collect(deadline if first_wait is None else min(first_wait, deadline))
    now = dict(results)

    def finish() -> dict:
        collect(deadline - (time.monotonic() - started))
        for future in futures:
            if futures[future].pk not in results:
                results[futures[future].pk] = FetchError("Took too long this time; it is tried again on your next search.")
        pool.shutdown(wait=False, cancel_futures=True)
        return results

    return now, finish


def _prefetch(sources: list[JobSource], roles: list[str] | None = None, jooble_key: str = "", on_progress=None) -> dict[int, object]:
    """Every source's answer, waiting up to the overall deadline (see _prefetch_staged for the two-stage version)."""
    _, finish = _prefetch_staged(sources, roles, jooble_key, on_progress=on_progress)
    return finish()


def _worker(run_id: int):
    try:
        run = ScanRun.objects.select_related("owner").get(pk=run_id)
        owner = run.owner
        config = SiteConfig.for_user(owner)
        profile = UserProfile.for_user(owner)
        areas = list(owner.search_areas.all())
        roles = _roles(owner)
        skill_terms = _skill_terms(owner)
        cv_text = knowledge.all_candidate_text(config, owner)
        min_overlap = settings.STILLOPEN_SKILL_MATCH_MIN_OVERLAP
        existing = _existing_urls(owner)
        existing_jobs = _existing_job_keys(owner)
        existing_triples = _existing_triples(owner)
        default_status = Status.objects.filter(bucket__is_closed=False).order_by("order").first() or Status.objects.first()
        room = max(0, settings.STILLOPEN_MAX_APPLICATIONS - Application.objects.filter(owner=owner).count())
        new_cap = max(0, settings.STILLOPEN_SCAN_MAX_NEW)
        per_company_cap = max(0, settings.STILLOPEN_SCAN_MAX_PER_COMPANY)
        from_company: Counter = Counter()
        today = timezone.localdate()
        sources = list(searchable_sources(owner))
        state = {"common": set(), "capped": False}

        def reading(count):
            ScanRun.objects.filter(pk=run.pk).update(done=count)
            run.done = count

        # Stage 1 starts as soon as the fast majority has answered; stage 2 adds what the slow hosts bring.
        answered, finish = _prefetch_staged(
            sources, roles, SiteConfig.load().effective_jooble_key, on_progress=reading,  # key read here: threads must not touch the database
            first_wait=settings.STILLOPEN_SCAN_FIRST_WAIT_SECONDS,
        )

        def gather(batch: list, fetched: dict) -> list:
            """Read each source's postings: record what was seen, and collect every clear, in-area, not-yet-tracked match."""
            corpus_total, corpus_counts, memo = _read_corpus(fetched, skill_terms)
            if not state["common"]:
                state["common"] = _common_from(corpus_total, corpus_counts, settings.STILLOPEN_SCAN_GENERIC_SHARE)
                if state["common"]:
                    cache.set("scan-common-terms", frozenset(state["common"]), 7 * 24 * 3600)  # a later one-off "Check my fit" scores the same way
            common = state["common"]
            found_here = []
            for source in batch:
                entry = ScanLogEntry(run=run, source_name=source.name, connector=source.connector)
                try:
                    postings = fetched[source.pk]
                    if isinstance(postings, Exception):
                        raise postings
                    entry.found = len(postings)
                    fresh = []
                    seen_today = set(PostingSighting.objects.filter(seen_date=today, posting__source=source).values_list("posting__url", flat=True))
                    for p in postings:
                        if not p["url"] or not p["title"]:
                            continue
                        # Recorded regardless of match: a repost pattern is a property of the posting/company, not of any
                        # one person's target roles. Already recorded today (by anyone's search): no write.
                        if p["url"][:600] not in seen_today:
                            fresh.append(p)
                            seen_today.add(p["url"][:600])
                        role_matched = _matches(p["title"], roles)
                        skill_words, term_count = memo.get(id(p), (frozenset(), 0))
                        overlap = set() if role_matched else set(skill_words - common)
                        if not role_matched and len(overlap) < min_overlap:
                            continue
                        entry.matched += 1
                        company = p.get("company") or source.name
                        if (p["url"] in existing or _is_cross_source_duplicate(existing_jobs, company, p["title"], source)
                                or _triple(company, p["title"], p.get("location") or "") in existing_triples):
                            entry.duplicates += 1
                            continue
                        # Clear location mismatches are left out (every posting stays visible under All postings).
                        description = p.get("description") or ""
                        probe = Application(owner=owner, company=company, role=p["title"][:200], location_text=(p.get("location") or "")[:160], description=description)
                        found = geo.detect(probe.role, f"{probe.location_text}\n{description}")
                        # The feed's own LOCATION field decides the country, not prose in the description (a company calling
                        # itself "global" must not turn a United States only job into a worldwide one).
                        place_codes = geo.location_codes(probe.location_text)
                        if len(place_codes) == 1:
                            found["country"] = next(iter(place_codes))
                        elif probe.location_text:
                            found.pop("country", None)
                        for name, value in found.items():
                            if name != "location_text" or not probe.location_text:
                                setattr(probe, name, value)
                        if areas and (fit.clearly_outside(probe, areas, profile) or fit.region_outside(place_codes, areas, profile)):
                            entry.outside += 1
                            continue
                        area_state = fit.area_status(probe, areas, profile)
                        try:
                            thin = term_count < settings.STILLOPEN_SCAN_MIN_TERMS_TO_SCORE
                            result = None if thin or not cv_text.strip() else ai.keyword_match(description, cv_text, ignore=common)
                        except ai.AIError:
                            result = None
                        percent = result["match_percent"] if result else -1
                        found_here.append({
                            "rank": (0 if area_state == "yes" else 1, not role_matched, -percent, len(found_here)), "role_matched": role_matched,
                            "overlap": overlap, "p": p, "company": company, "source": source, "posting": None, "probe": probe,
                            "found": found, "result": result, "entry": entry,
                        })
                    record_sightings(source, fresh, today)
                except (FetchError, KeyError, ValueError) as exc:
                    entry.error = str(exc)[:300]
                except Exception as exc:  # noqa: BLE001 - recorded on the entry, the search continues with the next source
                    entry.error = str(exc)[:300]
                entry.save()
                run.found += entry.found
                run.save(update_fields=["found"])
            return found_here

        def add_best(candidates: list, limit: int) -> None:
            """Add the best of `candidates` until `limit` jobs have been added in total: ones that clearly fit a search area
            first, then ones that fit a listed role, then by how well the person's own CV covers the posting."""
            nonlocal room
            candidates.sort(key=lambda item: item["rank"])
            touched = {}
            for item in candidates:
                if room <= 0:
                    run.error = (
                        f"Stopped early: you're at your {settings.STILLOPEN_MAX_APPLICATIONS}-job tracker limit. "
                        "Delete some roles, or raise STILLOPEN_MAX_APPLICATIONS, then search again."
                    )
                    break
                if limit and run.added >= limit:
                    state["capped"] = limit >= new_cap
                    break
                p, probe, found, result, entry = item["p"], item["probe"], item["found"], item["result"], item["entry"]
                company_key = item["company"].strip().lower()
                if per_company_cap and from_company[company_key] >= per_company_cap:
                    continue  # a fair spread: one employer cannot fill the whole list
                triple = _triple(item["company"], p["title"], p.get("location") or "")
                if (p["url"] in existing or _is_cross_source_duplicate(existing_jobs, item["company"], p["title"], item["source"])
                        or triple in existing_triples):
                    continue  # the same job on two sources, or the same role posted again for another team
                posting = Posting.objects.filter(source=item["source"], url=p["url"][:600]).first()
                app = Application(
                    owner=owner, company=item["company"][:160], role=p["title"][:200], url=p["url"][:600],
                    location_text=(probe.location_text or "")[:160], description=probe.description, status=default_status,
                    description_is_excerpt=bool(probe.description.strip()), found_date=today, posting=posting,
                    **{k: getattr(probe, k) for k in found if k != "location_text"},
                )
                if found:
                    app.details_source = "detected"
                app.save()
                if result:
                    ai.store_result(app, result, config, "keywords", note="found by search")
                if not item["role_matched"]:
                    Event.objects.create(
                        application=app, kind="note",
                        text=f"Found by skill match, not a listed target role -- shared: {', '.join(sorted(item['overlap'])[:6])}",
                    )
                existing.add(p["url"])
                from_company[company_key] += 1
                existing_triples.add(triple)
                existing_jobs.setdefault(_job_key(item["company"], p["title"]), set()).add(item["source"].pk)
                entry.added += 1
                touched[id(entry)] = entry
                run.added += 1
                run.added_ids.append(app.pk)
                room -= 1
                run.save(update_fields=["added", "added_ids"])  # visible to the dashboard the moment it exists
            for entry in touched.values():
                entry.save(update_fields=["added"])

        stage_one = [s for s in sources if s.pk in answered]
        slow = [s for s in sources if s.pk not in answered]
        first_batch = min(new_cap, settings.STILLOPEN_SCAN_FIRST_BATCH) if (slow and new_cap) else new_cap
        add_best(gather(stage_one, answered), first_batch)

        if slow:  # the slow hosts: whatever they bring competes for the rest of the cap
            late = finish()
            add_best(gather(slow, {s.pk: late[s.pk] for s in slow}), new_cap)
        else:
            finish()
        if state["capped"]:
            run.note = f"Showing the {new_cap} best new matches. Search again later for more; the rest are still under All postings."
        run.done = len(sources)
        run.save(update_fields=["added", "added_ids", "error", "note", "done"])
        PostingSighting.objects.filter(seen_date__lt=today - timedelta(days=180)).delete()
    except Exception as exc:  # noqa: BLE001 - recorded on the run
        ScanRun.objects.filter(pk=run_id).update(error=str(exc)[:500])
    finally:
        ScanRun.objects.filter(pk=run_id).update(running=False, finished_at=timezone.now())
        connections.close_all()


def current_run(owner) -> ScanRun | None:
    run = ScanRun.objects.filter(owner=owner).first()
    if run and run.running and timezone.now() - run.started_at > STALE_AFTER:
        run.running = False
        run.error = run.error or "timed out"
        run.finished_at = timezone.now()
        run.save()
    return run


def start_run(owner, background: bool = True) -> ScanRun:
    """One scan at a time per person; it only ever creates applications owned by that person."""
    existing = current_run(owner)
    if existing and existing.running:
        return existing
    run = ScanRun.objects.create(owner=owner, total=searchable_sources(owner).count())
    if background:
        threading.Thread(target=_worker, args=(run.pk,), daemon=True).start()
    else:
        _worker(run.pk)
        run.refresh_from_db()
    return run


def scan_digest_text(apps) -> str:
    lines = ["New jobs matching your search on StillOpen:", ""]
    for app in apps:
        where = f" ({app.location_text})" if app.location_text else ""
        lines.append(f"- {app.company} - {app.role}{where}")
        if app.url:
            lines.append(f"  {app.url}")
    lines += ["", "They are saved on your dashboard. Open it to check each fit and decide what to apply to.",
              "Turn these emails off any time under Profile > Job alerts."]
    return "\n".join(lines)


def send_scan_digest(owner, run: ScanRun) -> bool:
    """One email per person per scheduled run listing what that run added. Nothing is sent when nothing was added,
    or when the person has no verified address."""
    from allauth.account.models import EmailAddress
    from django.core.mail import send_mail

    apps = list(Application.objects.filter(owner=owner, pk__in=run.added_ids))
    if not apps:
        return False
    if not EmailAddress.objects.filter(user=owner, email=owner.email, verified=True).exists():
        return False
    count = len(apps)
    send_mail(
        subject=f"StillOpen: {count} new job{'s' if count != 1 else ''} for you",
        message=scan_digest_text(apps),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[owner.email],
        fail_silently=False,
    )
    return True


def maybe_auto_start(owner) -> ScanRun | None:
    """Search on the person's behalf when they open their dashboard and their last search is older than
    `SiteConfig.auto_scan_hours` (0 turns it off). No button, no cron, no AI: jobs are simply there. Runs only for
    someone who has said what they want (a target role or a CV), never twice at once, and never more often than that
    interval, whether or not the last search found anything."""
    if not settings.STILLOPEN_AUTO_SCAN:
        return None
    hours = SiteConfig.load().auto_scan_hours
    if hours <= 0:
        return None
    profile = UserProfile.for_user(owner)
    if not (profile.target_roles.strip() or (profile.profile_cv or "").strip()):
        return None
    if not searchable_sources(owner).exists():
        return None
    last = ScanRun.objects.filter(owner=owner).first()
    if last is not None:
        if last.running and timezone.now() - last.started_at <= STALE_AFTER:
            return None
        if timezone.now() - last.started_at < timedelta(hours=hours):
            return None
    return start_run(owner)
