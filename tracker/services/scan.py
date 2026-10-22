"""Search configured job boards for postings matching your target roles.

Zero-token: Greenhouse, Lever and Ashby all publish a plain public JSON endpoint for their job boards. Finding a
posting costs one HTTP GET per enabled JobSource, no AI call. Scoring/tailoring a posting once it's in your
tracker still goes through the normal (optional, BYOK) AI path -- this module only discovers and records it.

A posting is matched against your own UserProfile.target_roles (simple case-insensitive phrase containment,
the same zero-token approach career-ops' own title_filter uses) before anything is saved, and a posting whose
URL you already track is skipped as a duplicate rather than re-added.
"""
import re
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connections
from django.utils import timezone

from tracker.models import Application, JobSource, ScanLogEntry, ScanRun, Status, UserProfile
from tracker.services import geo
from tracker.services.netguard import FetchError, safe_get

STALE_AFTER = timedelta(minutes=20)
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _roles(owner) -> list[str]:
    profile = UserProfile.for_user(owner)
    return [r.strip().lower() for r in profile.target_roles.splitlines() if r.strip()]


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
                    if not p["url"] or not p["title"] or not _matches(p["title"], roles):
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
