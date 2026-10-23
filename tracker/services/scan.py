"""Search configured job boards for postings matching your target roles.

Zero-token: Greenhouse, Lever and Ashby all publish a plain public JSON endpoint for their job boards. Finding a
posting costs one HTTP GET per enabled JobSource, no AI call. Scoring/tailoring a posting once it's in your
tracker still goes through the normal (optional, BYOK) AI path -- this module only discovers and records it.

A posting is matched against your own UserProfile.target_roles (simple case-insensitive phrase containment,
the same zero-token approach career-ops' own title_filter uses) before anything is saved, and a posting whose
URL you already track is skipped as a duplicate rather than re-added.

Every posting fetched -- matched or not -- is also recorded as a `Posting` sighting (see record_sighting/
repost_signal below), shared across everyone watching that source. This is what a repost/ghost-job pattern is
read from later: a company re-listing the same role under a new URL shows up as several Postings sharing one
title_key at the same source, seen across more than one calendar day. Two concurrent openings posted the same
day are not flagged -- same discipline as career-ops' own detect-reposts.mjs (2+ distinct URLs, 2+ distinct
scan dates). This is an observation, never a verdict: a real company can legitimately re-post a role.
"""
import re
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connections
from django.utils import timezone

from tracker.models import Application, JobSource, Posting, PostingSighting, ScanLogEntry, ScanRun, Status, UserProfile
from tracker.services import geo
from tracker.services.netguard import FetchError, safe_get

STALE_AFTER = timedelta(minutes=20)
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _roles(owner) -> list[str]:
    profile = UserProfile.for_user(owner)
    return [r.strip().lower() for r in profile.target_roles.splitlines() if r.strip()]


def title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())[:300]


def record_sighting(source: JobSource, title: str, url: str, location: str, seen_date=None) -> Posting:
    """Upsert the Posting for (source, url) and mark it seen today (or `seen_date`, for tests)."""
    seen_date = seen_date or timezone.localdate()
    posting, _ = Posting.objects.update_or_create(
        source=source, url=url[:600],
        defaults={"title": title[:300], "title_key": title_key(title), "location": (location or "")[:160]},
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


def fetch_greenhouse(token: str) -> list[dict]:
    resp = safe_get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false", timeout=20)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    out = []
    for j in resp.json().get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "location": (j.get("location") or {}).get("name", ""),
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
        existing = _existing_urls(owner)
        default_status = Status.objects.filter(bucket__is_closed=False).order_by("order").first() or Status.objects.first()
        room = max(0, settings.STILLOPEN_MAX_APPLICATIONS - Application.objects.filter(owner=owner).count())
        capped = False
        for source in JobSource.objects.filter(enabled=True):
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
                    posting = record_sighting(source, p["title"], p["url"], p.get("location") or "")
                    if not _matches(p["title"], roles):
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
                        company=source.name,
                        role=p["title"][:200],
                        url=p["url"][:600],
                        location_text=(p.get("location") or "")[:160],
                        status=default_status,
                        found_date=timezone.localdate(),
                        posting=posting,
                    )
                    app.save()
                    geo.fill_details(app)
                    existing.add(p["url"])
                    entry.added += 1
                    run.added += 1
                    room -= 1
            except (FetchError, KeyError, ValueError) as exc:
                entry.error = str(exc)[:300]
            except Exception as exc:  # noqa: BLE001 - recorded on the entry, scan continues with the next source
                entry.error = str(exc)[:300]
            entry.save()
            run.found += entry.found
            run.done += 1
            run.save(update_fields=["done", "found", "added"])
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
    run = ScanRun.objects.create(owner=owner, total=JobSource.objects.filter(enabled=True).count())
    if background:
        threading.Thread(target=_worker, args=(run.pk,), daemon=True).start()
    else:
        _worker(run.pk)
        run.refresh_from_db()
    return run
