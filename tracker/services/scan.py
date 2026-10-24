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
import re
import threading
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import connections
from django.utils import timezone

from tracker.models import (
    Application, Event, JobSource, Posting, PostingSighting, ScanLogEntry, ScanRun, SiteConfig, Status, UserProfile,
)
from tracker.services import geo, knowledge
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


def _matches(title: str, roles: list[str]) -> bool:
    if not roles or not title:
        return False
    t = title.lower()
    return any(r in t for r in roles)


def _blurb(raw_html: str, limit: int = 4000) -> str:
    """Plain text from an HTML description field, trimmed -- only ever used for skill-term overlap, never
    stored or shown, so a few KB of context is plenty and keeps per-posting parsing cheap."""
    return html_to_text(raw_html or "")[:limit] if raw_html else ""


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
    resp = safe_get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("content", []):
        posting_id = j.get("id", "")
        out.append({
            "title": j.get("name", ""),
            "url": f"https://jobs.smartrecruiters.com/{token}/{posting_id}" if posting_id else "",
            "location": (j.get("location") or {}).get("fullLocation", ""),
        })
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


def _fetch(connector: str, token: str) -> list[dict]:
    # Resolved by name against this module's own namespace (not a dict built at import time) so that
    # mock.patch("tracker.services.scan.fetch_greenhouse", ...) in tests reaches the call that's actually made.
    fetcher = globals().get(f"fetch_{connector}")
    if fetcher is None:
        raise FetchError(f"Unknown connector: {connector}")
    return fetcher(token)


def _existing_urls(owner) -> set[str]:
    return set(Application.objects.filter(owner=owner).exclude(url="").values_list("url", flat=True))


def _worker(run_id: int):
    try:
        run = ScanRun.objects.select_related("owner").get(pk=run_id)
        owner = run.owner
        roles = _roles(owner)
        skill_terms = _skill_terms(owner)
        min_overlap = settings.STILLOPEN_SKILL_MATCH_MIN_OVERLAP
        existing = _existing_urls(owner)
        default_status = Status.objects.filter(bucket__is_closed=False).order_by("order").first() or Status.objects.first()
        room = max(0, settings.STILLOPEN_MAX_APPLICATIONS - Application.objects.filter(owner=owner).count())
        capped = False
        for source in JobSource.for_user(owner, enabled=True):
            entry = ScanLogEntry(run=run, source_name=source.name, connector=source.connector)
            try:
                if not TOKEN_RE.match(source.board_token):
                    raise FetchError("Invalid board token.")
                postings = _fetch(source.connector, source.board_token)
                entry.found = len(postings)
                for p in postings:
                    if not p["url"] or not p["title"]:
                        continue
                    # Recorded regardless of match: a repost pattern is a property of the posting/company,
                    # not of any one person's target roles, so it should build up even from scans that match
                    # nothing for this particular user.
                    posting = record_sighting(source, p["title"], p["url"], p.get("location") or "", company=p.get("company"))
                    role_matched = _matches(p["title"], roles)
                    overlap = set() if role_matched else _skill_overlap(
                        f"{p['title']} {p.get('description', '')}", skill_terms,
                    )
                    if not role_matched and len(overlap) < min_overlap:
                        continue
                    entry.matched += 1
                    if p["url"] in existing:
                        entry.duplicates += 1
                        continue
                    if room <= 0:
                        capped = True
                        break
                    app = Application(
                        owner=owner,
                        company=p.get("company") or source.name,
                        role=p["title"][:200],
                        url=p["url"][:600],
                        location_text=(p.get("location") or "")[:160],
                        status=default_status,
                        found_date=timezone.localdate(),
                        posting=posting,
                    )
                    app.save()
                    geo.fill_details(app)
                    if not role_matched:
                        Event.objects.create(
                            application=app, kind="note",
                            text=f"Found by skill match, not a listed target role -- shared: {', '.join(sorted(overlap)[:6])}",
                        )
                    existing.add(p["url"])
                    entry.added += 1
                    run.added += 1
                    run.added_ids.append(app.pk)
                    room -= 1
            except (FetchError, KeyError, ValueError) as exc:
                entry.error = str(exc)[:300]
            except Exception as exc:  # noqa: BLE001 - recorded on the entry, scan continues with the next source
                entry.error = str(exc)[:300]
            entry.save()
            run.found += entry.found
            run.done += 1
            run.save(update_fields=["done", "found", "added", "added_ids"])
            if capped:
                run.error = (
                    f"Stopped early: you're at your {settings.STILLOPEN_MAX_APPLICATIONS}-job tracker limit. "
                    "Delete some roles, or raise STILLOPEN_MAX_APPLICATIONS, then search again."
                )
                run.save(update_fields=["error"])
                break
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
    run = ScanRun.objects.create(owner=owner, total=JobSource.for_user(owner, enabled=True).count())
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
