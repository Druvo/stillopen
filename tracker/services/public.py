"""What the public pages (landing page and job board) show, and how they stay fresh.

Only openings from site-wide sources marked "show publicly" appear, only ones seen in a recent refresh (an opening nobody has
seen for a few days is treated as gone: Google and several sources require expired jobs to be removed), and never anything
from a person's own boards. Each opening shows only an excerpt and a credit link; the full posting stays with its owner."""
import threading
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.db.models import Count, Max
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.text import slugify

from tracker.models import JobSource, Posting
from tracker.services import geo

BOARD_CONNECTORS = ("greenhouse", "lever", "ashby", "smartrecruiters", "recruitee")
# Sources that ask for a visible link back to them. Employer boards credit the employer instead.
CREDITS = {
    "remoteok": ("Remote OK", "https://remoteok.com"),
    "himalayas": ("Himalayas", "https://himalayas.app"),
    "jobicy": ("Jobicy", "https://jobicy.com"),
    "arbeitnow": ("Arbeitnow", "https://www.arbeitnow.com"),
}
STATS_KEY = "public-stats"
REFRESH_LOCK = "public-refresh-lock"
REFRESH_TRIED = "public-refresh-tried"


def active_cutoff():
    return timezone.now() - timedelta(days=settings.STILLOPEN_PUBLIC_ACTIVE_DAYS)


def public_sources():
    return JobSource.objects.filter(owner__isnull=True, enabled=True, show_publicly=True).exclude(connector="jooble")


def public_postings():
    """Every opening the public may see right now."""
    return Posting.objects.filter(
        source__owner__isnull=True, source__enabled=True, source__show_publicly=True, last_seen_at__gte=active_cutoff(),
    ).select_related("source")


def credit_for(posting) -> dict:
    """Who to thank, and where the full posting lives. The link is the posting's own address, unchanged."""
    connector = posting.source.connector
    if connector in CREDITS:
        label, home = CREDITS[connector]
        return {"label": label, "home": home, "url": posting.url, "kind": "source"}
    return {"label": f"{posting.company} careers", "home": "", "url": posting.url, "kind": "employer"}


def slug_for(posting) -> str:
    return slugify(f"{posting.title} {posting.company}")[:80] or "opening"


def location_label(posting) -> str:
    if posting.location:
        return posting.location
    return "Remote" if posting.remote else "Location not stated"


def stats(refresh: bool = False) -> dict:
    """Live numbers for the landing page and board, cached for half an hour."""
    if not refresh:
        hit = cache.get(STATS_KEY)
        if hit is not None:
            return hit
    base = public_postings()
    total = base.count()
    now = timezone.now()
    new_today = base.filter(first_seen_at__gte=now - timedelta(days=1)).count()
    first_ever = Posting.objects.order_by("first_seen_at").values_list("first_seen_at", flat=True).first()
    history_days = (now - first_ever).days if first_ever else 0
    countries = list(
        base.exclude(country="").values("country").annotate(n=Count("id")).order_by("-n")[:8]
    )
    by_day = {
        row["day"]: row["n"]
        for row in base.filter(first_seen_at__gte=now - timedelta(days=14)).annotate(day=TruncDate("first_seen_at")).values("day").annotate(n=Count("id"))
    }
    today = timezone.localdate()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    kinds = {row["source__connector"]: row["n"] for row in base.values("source__connector").annotate(n=Count("id"))}
    boards = sum(n for c, n in kinds.items() if c in BOARD_CONNECTORS)
    result = {
        "total": total,
        "companies": base.values("company").distinct().count(),
        "countries": base.exclude(country="").values("country").distinct().count(),
        "remote": base.filter(remote=True).count(),
        "sources_searched": JobSource.objects.filter(owner__isnull=True, enabled=True).count(),
        "sources_public": public_sources().count(),
        # A fresh install loads everything on day one; "new today" and a day-by-day chart would only describe that import.
        "new_today": new_today if total and new_today / total <= 0.5 else None,
        "by_country": [{"code": c["country"], "name": geo.country_name(c["country"]), "n": c["n"]} for c in countries],
        "by_day": [{"day": d, "n": by_day.get(d, 0)} for d in days] if history_days >= 3 else [],
        "boards": boards,
        "feeds": total - boards,
        "credits": sorted({CREDITS[c][0]: CREDITS[c][1] for c in kinds if c in CREDITS}.items()),
        "updated": base.aggregate(m=Max("last_seen_at"))["m"],
    }
    cache.set(STATS_KEY, result, 1800)
    return result


def latest(n: int = 8) -> list:
    """The newest openings, at most one per employer so the strip shows variety."""
    seen, out = set(), []
    for posting in public_postings().order_by("-first_seen_at", "-pk")[:400]:
        key = posting.company.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(posting)
        if len(out) >= n:
            break
    return out


# --- keeping the board fresh -----------------------------------------------------------------------------

def is_stale() -> bool:
    newest = Posting.objects.filter(source__owner__isnull=True, source__show_publicly=True).aggregate(m=Max("last_seen_at"))["m"]
    return newest is None or timezone.now() - newest > timedelta(hours=settings.STILLOPEN_PUBLIC_REFRESH_HOURS)


def refresh_now() -> dict:
    """Read every public source and mark what is still listed as seen today. Needs no person and no AI."""
    from tracker.services import scan

    sources = list(public_sources())
    _, finish = scan._prefetch_staged(sources, [], "")
    fetched = finish()
    today = timezone.localdate()
    seen = errors = 0
    for source in sources:
        postings = fetched.get(source.pk)
        if isinstance(postings, Exception) or postings is None:
            errors += 1
            continue
        postings = [p for p in postings if p.get("url") and p.get("title")]
        scan.record_sightings(source, postings, today)
        seen += len(postings)
    cache.delete(STATS_KEY)
    return {"sources": len(sources), "errors": errors, "postings": seen}


def refresh_if_stale() -> bool:
    """Called when an anonymous visitor arrives: if the board is out of date, refresh it in the background, at most once an
    hour and never twice at once. Visitors never wait for it. Returns whether a refresh was started."""
    if not settings.STILLOPEN_PUBLIC_AUTO_REFRESH or not is_stale():
        return False
    if not cache.add(REFRESH_TRIED, 1, 3600):  # tried recently, even if it found nothing
        return False
    if not cache.add(REFRESH_LOCK, 1, 1800):
        return False

    def work():
        try:
            refresh_now()
        except Exception:  # noqa: BLE001 - a failed refresh must never reach a visitor
            pass
        finally:
            cache.delete(REFRESH_LOCK)
            connections.close_all()

    threading.Thread(target=work, daemon=True).start()
    return True
